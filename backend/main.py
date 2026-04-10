import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db.database import init_db
from backend.api.routes import router
from backend.scheduler import start_scheduler

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.environ.get("VERCEL"):
        # Serverless: no persistent background scheduler.
        # Refresh the watchlist once on cold start so the UI isn't empty.
        from backend.watchlist import refresh_watchlist
        refresh_watchlist()
    else:
        start_scheduler()
    yield


app = FastAPI(title="Sentiment Scanner", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
