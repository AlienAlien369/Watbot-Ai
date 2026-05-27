-- SQL schema for watbotai POC
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  doc_name TEXT,
  chunk_index INT,
  text_content TEXT,
  embedding_vector FLOAT8[],
  created_at TIMESTAMPTZ DEFAULT now()
);
