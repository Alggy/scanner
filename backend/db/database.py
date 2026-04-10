from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "scanner.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.db import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=engine)
    # Safe migration: add published_at if it doesn't exist yet
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("posts")]
    if "published_at" not in cols:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE posts ADD COLUMN published_at DATETIME"))
            conn.commit()
