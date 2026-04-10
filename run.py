"""
Entry point: starts FastAPI + APScheduler.

Usage:
  python run.py

Requires a .env file in this directory (copy .env.example and fill in values).
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render injects $PORT
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
