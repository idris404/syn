import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/agents", tags=["agents"])

_HISTORY_KEY = "syn:runs:history"
_ACTIVE_KEY = "syn:runs:active"


class RunRequest(BaseModel):
    targets: list[dict] | None = None


async def _get_redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.post("/run")
async def start_run(body: RunRequest, background_tasks: BackgroundTasks) -> dict:
    from app.scheduler import run_agent_pipeline

    # Check if a run is already active
    client = await _get_redis()
    try:
        active = await client.get(_ACTIVE_KEY)
        if active:
            raise HTTPException(status_code=409, detail=f"Run already in progress: {active}")
    finally:
        await client.aclose()

    import uuid
    run_id = str(uuid.uuid4())

    background_tasks.add_task(run_agent_pipeline, run_id=run_id, targets=body.targets)

    return {"run_id": run_id, "status": "started"}


@router.get("/runs")
async def list_runs() -> dict:
    client = await _get_redis()
    try:
        raw = await client.get(_HISTORY_KEY)
        history: list = json.loads(raw) if raw else []
        active = await client.get(_ACTIVE_KEY)
    finally:
        await client.aclose()

    runs = []
    for entry in reversed(history):
        runs.append({
            "run_id": entry.get("run_id"),
            "started_at": entry.get("started_at"),
            "status": "active" if entry.get("run_id") == active else entry.get("status", "done"),
            "report_title": entry.get("report_title"),
            "notion_url": entry.get("notion_url"),
        })

    return {"runs": runs, "active_run_id": active}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    client = await _get_redis()
    try:
        raw = await client.get(f"syn:runs:{run_id}")
        active = await client.get(_ACTIVE_KEY)
    finally:
        await client.aclose()

    if not raw:
        if active == run_id:
            return {"run_id": run_id, "status": "in_progress"}
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    state = json.loads(raw)
    return state
