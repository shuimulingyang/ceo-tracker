"""
server.py — FastAPI backend for Crypto CEO Tracker.
Run:  python server.py
Then open http://localhost:8000
"""

import os
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import get_articles, get_stats, init_db
from fetcher import CEOS, fetch_all_news

scheduler = AsyncIOScheduler()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    print("Database initialised.")

    print("Running initial data fetch (this may take ~30 seconds)...")
    await fetch_all_news()

    scheduler.add_job(fetch_all_news, "interval", minutes=30, id="auto_refresh")
    scheduler.start()
    print("Scheduler started — auto-refresh every 30 minutes.")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    print("Scheduler stopped.")


app = FastAPI(title="Crypto CEO Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/articles")
async def list_articles(
    ceo: str = Query(default="all", description="CEO name or 'all'"),
    search: str = Query(default="", description="Keyword search"),
    limit: int = Query(default=60, le=200),
    offset: int = Query(default=0, ge=0),
):
    articles = get_articles(ceo=ceo, search=search, limit=limit, offset=offset)
    return {"articles": articles, "count": len(articles)}


@app.get("/api/ceos")
async def list_ceos():
    return {
        "ceos": {
            name: {
                "exchange": info["exchange"],
                "role": info.get("role", "CEO"),
                "color": info["color"],
                "twitter": info["twitter"],
            }
            for name, info in CEOS.items()
        }
    }


@app.get("/api/stats")
async def stats():
    return get_stats()


@app.post("/api/refresh")
async def refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_all_news)
    return {"message": "Refresh started in background"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
