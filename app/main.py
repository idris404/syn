from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.database import create_tables
from app.services.qdrant_service import ensure_collections


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SYN — initializing database and vector store...")
    await create_tables()
    await ensure_collections()

    from app.scheduler import init_scheduler
    init_scheduler(app)

    logger.info("SYN ready.")
    yield

    from app.scheduler import scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("SYN shutting down.")


app = FastAPI(title="SYN", description="Autonomous pharma/biotech R&D monitoring agent", lifespan=lifespan)

from app.api import agent_runs, ingest, papers, rag, trials  # noqa: E402

app.include_router(trials.router)
app.include_router(ingest.router)
app.include_router(papers.router)
app.include_router(rag.router)
app.include_router(agent_runs.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "syn"}
