import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.storage.ledger import init_db
from app.ingest.poller import start_scheduler, stop_scheduler
from app.api import search as search_api
from app.api import ask as ask_api
from app.api import papers as papers_api
from app.api import auth as auth_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="bio-view", lifespan=lifespan)

app.include_router(auth_api.router, tags=["auth"])
app.include_router(search_api.router, tags=["search"])
app.include_router(ask_api.router, tags=["ask"])
app.include_router(papers_api.router, tags=["papers"])


@app.get("/health")
def health():
    return {"ok": True}


# Serve the built frontend when present (production / Docker)
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(STATIC_DIR / "index.html")
