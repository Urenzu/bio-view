import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.storage.ledger import init_db
from app.ingest.poller import start_scheduler, stop_scheduler
from app.api import search as search_api
from app.api import ask as ask_api
from app.api import papers as papers_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="bio-view", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_api.router, tags=["search"])
app.include_router(ask_api.router, tags=["ask"])
app.include_router(papers_api.router, tags=["papers"])


@app.get("/health")
def health():
    return {"ok": True}
