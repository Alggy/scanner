from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

# On Vercel the only writable directory is /tmp.
# On Render/local, DATABASE_PATH env var overrides; defaults to scanner.db in project root.
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/scanner.db"
else:
    _default = os.path.join(os.path.dirname(__file__), "..", "..", "scanner.db")
    DB_PATH = os.environ.get("DATABASE_PATH", os.path.abspath(_default))

DATABASE_URL = f"sqlite:///{DB_PATH}"

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
