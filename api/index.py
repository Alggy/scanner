"""
Vercel entry point.
Adds the project root to sys.path so the `backend` package is importable,
then re-exports the FastAPI `app` object for Vercel to serve.
"""
import sys
import os

# Project root = parent of this file's directory (scanner/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app  # noqa: F401 — Vercel discovers `app` from this module
