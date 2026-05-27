# app/db.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, exc
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./watbotai.db")

# create engine (may point to Postgres or SQLite)
engine = create_engine(DATABASE_URL, future=True)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    doc_name = Column(String(1024))
    chunk_index = Column(Integer)
    text_content = Column(Text)

def init_db():
    """
    Create tables for the configured engine.
    If an OperationalError occurs connecting to Postgres, fall back to a local SQLite file for dev.
    """
    global engine, DATABASE_URL
    try:
        Base.metadata.create_all(bind=engine)
    except exc.OperationalError as e:
        # If Postgres DB not available, fall back to local SQLite for local dev convenience
        if isinstance(e, exc.OperationalError) and (DATABASE_URL.startswith("postgres") or DATABASE_URL.startswith("postgresql")):
            fallback = "sqlite:///./watbotai.db"
            engine = create_engine(fallback, future=True)
            SessionLocal.configure(bind=engine)
            Base.metadata.create_all(bind=engine)
            print("WARNING: Could not connect to Postgres DB. Falling back to SQLite at ./watbotai.db")
        else:
            raise
