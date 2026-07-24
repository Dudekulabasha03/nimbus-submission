"""
database.py – SQLAlchemy engine, session, and dependency injection for Nimbus Insight.
SQLite DB is stored at ./data/nimbus.db for Docker volume persistence.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Resolve DB path relative to this file's directory so it works both locally and in Docker
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'nimbus.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI threading
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_migrate():
    """
    Run lightweight, idempotent schema migrations.
    Called once on startup — safe to run on existing databases.
    """
    with engine.connect() as conn:
        # Add file_hash column if it doesn't exist (SQLite supports ADD COLUMN)
        try:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE processing_jobs ADD COLUMN file_hash VARCHAR(32)"
                )
            )
            conn.commit()
            print("[db] Migration: added file_hash column.", flush=True)
        except Exception:
            # Column already exists — ignore
            pass

