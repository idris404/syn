import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models.paper import PaperRecord
from app.models.trial import ClinicalTrial

router = APIRouter(tags=["kpis"])


@router.get("/kpis")
async def get_kpis(db: AsyncSession = Depends(get_session)) -> dict:
    total_trials = (await db.execute(select(func.count()).select_from(ClinicalTrial))).scalar() or 0
    recruiting_trials = (
        await db.execute(
            select(func.count())
            .select_from(ClinicalTrial)
            .where(ClinicalTrial.status == "RECRUITING")
        )
    ).scalar() or 0
    total_papers = (await db.execute(select(func.count()).select_from(PaperRecord))).scalar() or 0

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    history_raw = await client.get("syn:runs:history")
    await client.aclose()

    history: list[dict] = []
    if history_raw:
        try:
            history = json.loads(history_raw)
        except json.JSONDecodeError:
            history = []

    last_run_at = history[-1].get("started_at") if history else None
    last_run_status = history[-1].get("status") if history else None

    return {
        "total_trials": total_trials,
        "recruiting_trials": recruiting_trials,
        "total_papers": total_papers,
        "total_reports": len(history),
        "last_run_at": last_run_at,
        "last_run_status": last_run_status,
    }