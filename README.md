# watbotai — Multi-tenant Document Q&A POC

This repository is a Proof-of-Concept (POC) for **watbotai**: a multi-tenant PDF document querying system.

## Features
- FastAPI backend with:
  - `POST /upload` — upload a PDF (multipart) with `tenant_id`
  - `POST /ask` — ask a question `{ "tenant_id": "...", "question": "..." }`
- Per-tenant ChromaDB vector collections using **fastembed** (BAAI/bge-small-en-v1.5)
- Retrieval of top-3 relevant chunks from the uploaded document
- LLM-powered answers via **Groq** (llama-3.1-8b-instant)
- React-style SPA frontend (plain HTML/JS) deployed on **Vercel**
- All secrets in `.env`
- `requirements.txt`, `Dockerfile`, and `render.yaml` for Render deployment

> NOTE: This is a POC. Keep your real secrets safe; do not hardcode real API keys.

---

## Quick start (local)

1. Create virtualenv and install:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables in `.env`:
```
GROQ_API_KEY=your_groq_api_key
```

3. Start the FastAPI app:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open `frontend/index.html` or visit the deployed Vercel URL.

---

## cURL examples

Upload a PDF:
```bash
curl -X POST "http://localhost:8000/upload" \
  -F "tenant_id=tenant_123" \
  -F "file=@./sample.pdf"
```

Ask a question:
```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "tenant_123", "question": "What is the main topic of this document?"}'
```

---

## Files of interest

- `app/main.py` — FastAPI application
- `app/streamlit_app.py` — Streamlit frontend (legacy)
- `app/static/widget.html` — Plain HTML widget
- `frontend/index.html` — SPA frontend (deployed on Vercel)
- `Dockerfile` — Container config for Render
- `render.yaml` — Render deployment config
- `requirements.txt` — pip packages

---

Enjoy!
