# watbotai — Minimal Multi-tenant POC

This repository is a Proof-of-Concept (POC) for **watbotai**: a multi-tenant document + chat system.

Features
- FastAPI backend with:
  - `POST /upload` — upload PDF (multipart) with `tenant_id`
  - `POST /ask` — ask a JSON question `{ "tenant_id": "...", "question": "..." }`
- PostgreSQL schema with `tenant_id` on every stored row (see `models.sql`)
- LangChain to split PDFs, OpenAI **text-embedding-ada-002** embeddings, store in local Chroma DB (per-tenant collection)
- Retrieval of top-3 chunks
- Chat via `gpt-3.5-turbo` using a pizza-ordering bot persona. Reply **includes** a hard-coded Stripe test Payment Link.
- Streamlit front page for uploading PDF and chatting
- Plain HTML widget (`static/widget.html`) suitable for GitHub Pages that POSTs to `/ask`
- All secrets in `.env` (sample `.env.example` provided)
- `requirements.txt`, `Dockerfile`, and usage examples (cURL + web demo)
- Single python folder, friendly for serverless deployments

> NOTE: This is a POC. Keep your real secrets safe; do not hardcode real API keys.

---

## Quick start (local)

1. Create virtualenv and install:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create a Postgres database and set environment variables in `.env` (see `.env.example`).

3. Start the FastAPI app:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Start Streamlit UI:
```bash
streamlit run app/streamlit_app.py
# opens at http://localhost:8501
```

5. Upload a PDF (via Streamlit or curl), then ask questions.

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
  -d '{"tenant_id": "tenant_123", "question": "I want a pepperoni pizza, please"}'
```

---

## Files of interest

- `app/main.py` — FastAPI application
- `app/db.py` — Postgres helper + schema helper
- `app/models.sql` — SQL to create table
- `app/streamlit_app.py` — Streamlit frontend
- `app/static/widget.html` — Plain HTML widget that POSTs to `/ask`
- `.env.example` — example environment variables
- `Dockerfile` — example container
- `requirements.txt` — pip packages

---

## Stripe test payment link

The bot inserts a test Stripe Payment Link in each reply:

`https://buy.stripe.com/test_14k9Aq7fG2bK2Qw9AE`

Replace with your own link as needed.

--- 

If you want I can walk through each file. Enjoy!