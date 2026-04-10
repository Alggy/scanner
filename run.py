"""
Entry point: starts FastAPI + APScheduler.

Usage:
  python run.py

Requires a .env file in this directory (copy .env.example and fill in values).
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
