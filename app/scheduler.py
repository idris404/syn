import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from agents.state import SynState

scheduler = AsyncIOScheduler()


async def run_agent_pipeline(run_id: str | None = None, targets: list[dict] | None = None) -> str:
    from agents.graph import build_graph
    import redis.asyncio as aioredis
    from app.config import settings

    run_id = run_id or str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    initial_state = SynState(
        run_id=run_id,
        started_at=started_at,
        targets=targets or [],
        plan_reasoning="",
        raw_results=[],
        sources_searched=[],
        analysis="",
        key_findings=[],
        competitor_updates=[],
        report_title="",
        report_body="",
        report_summary="",
        errors=[],
        current_agent="planner",
        status="planning",
    )

    # Mark run as active in Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis_client.set("syn:runs:active", run_id)
    except Exception as e:
        logger.warning(f"[Scheduler] Redis active set failed: {e}")
    finally:
        await redis_client.aclose()

    logger.info(f"[Scheduler] launching run_id={run_id}")
    try:
        graph = build_graph()
        await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": run_id}},
        )
        logger.info(f"[Scheduler] run complete: run_id={run_id}")
    except Exception as e:
        logger.error(f"[Scheduler] pipeline error: {e}")

    return run_id


def init_scheduler(app) -> None:
    scheduler.add_job(
        run_agent_pipeline,
        CronTrigger(hour=7, minute=0),
        id="daily_syn_run",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[Scheduler] APScheduler started — daily run at 07:00")
