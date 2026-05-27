# ------------------------------------------------------------
# 0.  ENV + STD-LIB
# ------------------------------------------------------------
import os
import io
import tempfile
import logging
from typing import List, Any, Dict
import chromadb
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List
import math
import traceback
from sentence_transformers import SentenceTransformer
st_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1",trust_remote_code=True)  

load_dotenv()
print("[STEP-0] .env loaded")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)


def _estimate_tokens(text: str) -> int:
    words = len(text.split())
    return math.ceil(words / 0.75)

# ------------------------------------------------------------
# 1.  SQLAlchemy – minimal in-memory SQLite for demo
# ------------------------------------------------------------
from sqlalchemy import create_engine, text, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class DocumentRow(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    doc_name = Column(String)
    chunk_index = Column(Integer)
    text_content = Column(Text)

SQLITE_URL = "sqlite:///./local.db"
engine = create_engine(SQLITE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
print("[STEP-1] SQLite engine & table created")

# ------------------------------------------------------------
# 2.  PDF / text utilities
# ------------------------------------------------------------
from pypdf import PdfReader, errors as pypdf_errors

class SimpleDoc:
    def __init__(self, page_content: str, metadata: Dict | None = None):
        self.page_content = page_content
        self.metadata = metadata or {}

def _parse_pdf_bytes_to_docs(contents: bytes) -> List[SimpleDoc]:
    print("[STEP-2a] _parse_pdf_bytes_to_docs() called")
    try:
        pdf_stream = io.BytesIO(contents)
        reader = PdfReader(pdf_stream, strict=False)
        pages_text: List[str] = []
        for i, p in enumerate(reader.pages):
            try:
                t = p.extract_text() or ""
            except Exception:
                t = ""
            pages_text.append(t)
        print(f"[STEP-2b] extracted {len(pages_text)} pages")
    except pypdf_errors.PdfReadError as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")
    docs = [SimpleDoc(txt, {"page": i}) for i, txt in enumerate(pages_text)]
    print("[STEP-2c] returning SimpleDoc list")
    return docs

def _split_text_into_chunks(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> List[str]:
    print(f"[STEP-2d] _split_text_into_chunks() – input len={len(text)}")
    if not text:
        return []
    step = max(1, chunk_size - chunk_overlap)
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += step
    print(f"[STEP-2e] produced {len(chunks)} chunks")
    return chunks

def _split_documents(docs: List[SimpleDoc], chunk_size: int = 800, chunk_overlap: int = 100 , tenant_id : str = "") -> List[SimpleDoc]:
    print("[STEP-2f] _split_documents() called")
    out: List[SimpleDoc] = []
    for d in docs:
        text = getattr(d, "page_content", "") or ""
        chunks = _split_text_into_chunks(text, chunk_size, chunk_overlap)
        if not chunks:
            out.append(SimpleDoc("", {**getattr(d, "metadata", {}), "chunk_index": 0}))
            continue
        for i, c in enumerate(chunks):
            meta = dict(getattr(d, "metadata", {}) or {})
            meta.update({"chunk_index": i, "tenant_id": tenant_id})  # <-- add this
            out.append(SimpleDoc(c, meta))
    print(f"[STEP-2g] returning {len(out)} chunked SimpleDocs")
    return out

# ------------------------------------------------------------
# 3.  Groq async client
# ------------------------------------------------------------
from groq import AsyncGroq, APIError, APIStatusError, APIConnectionError

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEYS") or os.getenv("OPENAI_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY required")
print("[STEP-3a] Groq API key found")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v1.5")
print(f"[STEP-3b] embedding model = {EMBEDDING_MODEL}")

async def _get_embeddings_for_texts(texts: List[str], **kw) -> List[List[float]]:
    print(f"[STEP-3c] local ST embedding – {len(texts)} texts")
    return st_model.encode(texts, normalize_embeddings=True).tolist()


# ------------------------------------------------------------
# 4.  ChromaDB client
# ------------------------------------------------------------
# -------------------------
# Replace _get_chroma_client_and_collection with this
# -------------------------
from chromadb import Client as ChromaClient, Settings

def _get_chroma_client_and_collection(tenant_id: str, persist_dir: str):
    """
    Robust chroma client creator that supports different chromadb versions.
    Returns (client, collection)
    """
    print(f"[STEP-4a] _get_chroma_client_and_collection() – tenant={tenant_id} persist_dir={persist_dir}")
    os.makedirs(persist_dir, exist_ok=True)

    # Create Settings object if available and use chromadb.Client(Settings(...))
    try:
        settings = Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_dir,
        )
        # Prefer the public Client constructor which is stable across versions
        client = ChromaClient(settings=settings)
        print(f"client --> {client}")
        print("[STEP-4x] chromadb.Client(settings=...) created")
    except Exception as e:
        # Fallback: try PersistentClient (older/newer installs)
        try:
            client = chromadb.PersistentClient(path=persist_dir)
            print("[STEP-4y] chromadb.PersistentClient(path=...) created (fallback)")
        except Exception as e2:
            print("[STEP-4z] chroma client creation failed:", e, e2)
            raise

    # Get or create collection robustly
    collection = None
    try:
        collection = client.get_collection(name=tenant_id)
        print("[STEP-4b] reused existing collection")
    except Exception:
        # collection does not exist → create it
        collection = client.create_collection(name=tenant_id)
        print("[STEP-4c] created new collection")

    return client, collection

# ------------------------------------------------------------
# 5.  FastAPI app
# ------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("watbotai")

STRIPE_TEST_LINK = os.getenv("STRIPE_TEST_LINK", "https://buy.stripe.com/test_14k9Aq7fG2bK2Qw9AE ")

app = FastAPI(title="watbotai POC (groq)")
print("[STEP-5a] FastAPI app instantiated")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    tenant_id: str
    question: str

# ---------- upload ----------
@app.post("/upload")
async def upload_pdf(tenant_id: str = Form(...), file: UploadFile = File(...)):
    print(f"[ENDPOINT-UPLOAD] hit – tenant={tenant_id} file={file.filename}")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF supported")

    contents = await file.read()
    print(f"[ENDPOINT-UPLOAD] read {len(contents)} bytes")
    docs = _parse_pdf_bytes_to_docs(contents)
    chunks = _split_documents(docs, chunk_size=800, chunk_overlap=100,tenant_id=tenant_id)
    texts = [getattr(c, "page_content", "") or "" for c in chunks]
    metadatas = [getattr(c, "metadata", {}) for c in chunks]
    ids = [f"{tenant_id}::{file.filename}::chunk_{i}" for i in range(len(chunks))]
    print(f"[ENDPOINT-UPLOAD] prepared {len(ids)} ids")

    embeddings = await _get_embeddings_for_texts(texts, model=EMBEDDING_MODEL)
    print(f"[ENDPOINT-UPLOAD] embeddings shape={len(embeddings)}x{len(embeddings[0])}")

    persist_dir = os.path.join(CHROMA_PERSIST_DIR, tenant_id)
    client, collection = _get_chroma_client_and_collection(tenant_id, persist_dir)

    try:
        collection.delete(ids=ids)
        print("[ENDPOINT-UPLOAD] old ids deleted")
    except Exception:
        print("[ENDPOINT-UPLOAD] nothing to delete")
    collection.add(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)
    print("[ENDPOINT-UPLOAD] vectors added to Chroma")

    # optional SQL record
    try:
        db = SessionLocal()
        insert_stmt = text(
            "INSERT INTO documents (tenant_id, doc_name, chunk_index, text_content) "
            "VALUES (:t, :n, :i, :c)"
        )
        for i, doc in enumerate(chunks):
            text_content = (getattr(doc, "page_content", "") or "")[:10000]
            db.execute(insert_stmt, {"t": tenant_id, "n": file.filename, "i": i, "c": text_content})
        db.commit()
        print("[ENDPOINT-UPLOAD] SQLite rows inserted")
    except Exception:
        logger.exception("DB insert failed (nonfatal)")
    finally:
        db.close()

    return {"status": "ok", "chunks_stored": len(chunks)}

# ---------- ask ----------
@app.post("/ask")
async def ask(req: AskRequest):
    print(f"[ENDPOINT-ASK] hit – tenant={req.tenant_id} question='{req.question}'")
    tenant_id = req.tenant_id.strip()
    question = req.question.strip()

    if not question:
        return {"answer": "Empty question.", "sources_returned": 0}

    # === 1. Embed question ===
    try:
        q_embedding = st_model.encode([question], normalize_embeddings=True).tolist()[0]
    except Exception:
        traceback.print_exc()
        return {"answer": "Embedding failed.", "sources_returned": 0}

    # === 2. Query ChromaDB ===
    persist_dir = os.path.join(CHROMA_PERSIST_DIR, tenant_id)
    client, collection = _get_chroma_client_and_collection(tenant_id, persist_dir)
    if collection is None:
        return {"answer": "No collection found.", "sources_returned": 0}

    try:
        result = collection.query(
            query_embeddings=[q_embedding],
            n_results=5,  # Let ChromaDB give top 5
            where={"tenant_id": tenant_id},  # 🔥 Filter by tenant
            include=["documents", "metadatas", "distances"]
        )
    except Exception:
        traceback.print_exc()
        return {"answer": "Chroma query failed.", "sources_returned": 0}

    docs = result["documents"][0] or []
    metas = result["metadatas"][0] or []
    distances = result["distances"][0] or []

    if not docs:
        return {"answer": "No relevant context found.", "sources_returned": 0}

    # === 3. Build context within token budget ===
    token_budget = 1700
    used = 0
    parts = []
    sources = []

    for doc, meta, dist in zip(docs, metas, distances):
        tokens = _estimate_tokens(doc)
        if used + tokens > token_budget:
            break
        parts.append(doc)
        sources.append({"meta": meta, "distance": dist})
        used += tokens

    print(f"The parts of context are : {parts}")

    context = "\n\n---\n\n".join(parts)

    # === 4. LLM call ===
    system_prompt = (
        "You are PizzaPal, a friendly pizza-ordering assistant. Keep answers short and helpful. "
        "Always include this Stripe test link at the end: " + STRIPE_TEST_LINK
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
    ]

    try:
        chat_resp = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=400,
            temperature=0.2,
        )
        answer = chat_resp.choices[0].message.content
    except Exception as e:
        import traceback
        traceback.print_exc()          # <-- full error to console
        print("[DEBUG] messages sent:", messages)   # also log the payload
        return {"answer": "LLM failed.", "sources_returned": len(sources)}


    if STRIPE_TEST_LINK not in answer:
        answer += "\n\nPayment link: " + STRIPE_TEST_LINK

    return {
        "answer": answer,
        "sources_returned": len(sources),
        "sources": [{"meta": s["meta"], "distance": s["distance"]} for s in sources]
    }
# ------------------------------------------------------------
# 6.  Root endpoint
# ------------------------------------------------------------
@app.get("/")
def root():
    print("[ENDPOINT-ROOT] hit")
    return {"service": "watbotai POC (groq)"}


@app.post("/debug/count")
def count_vectors(tenant_id: str):
    client, coll = _get_chroma_client_and_collection(tenant_id, os.path.join(CHROMA_PERSIST_DIR, tenant_id))
    return {"count": coll.count()}
# ------------------------------------------------------------
# 7.  Run
# ------------------------------------------------------------
if __name__ == "__main__":
    print("[STEP-7] starting uvicorn on 0.0.0.0:8000")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)