import asyncio
import time
from datetime import datetime, timezone

from loguru import logger

from agents.state import SynState
from app.config import settings
from app.services import rag_service

_INGESTION_TTL_HOURS = 24
_LAST_INGEST_KEY_PREFIX = "syn:ingestion:last:"

_SOURCE_TO_RAG = {
    "clinicaltrials": "trials",
    "pubmed": "papers",
    "biorxiv": "papers",
    "ema": "ema",
}


async def _last_ingestion_hours(redis_client, query: str) -> float:
    key = f"{_LAST_INGEST_KEY_PREFIX}{query.lower().replace(' ', '_')}"
    raw = await redis_client.get(key)
    if not raw:
        return float("inf")
    try:
        last_dt = datetime.fromisoformat(raw)
        delta = datetime.now(timezone.utc) - last_dt
        return delta.total_seconds() / 3600
    except Exception:
        return float("inf")


async def _mark_ingested(redis_client, query: str) -> None:
    key = f"{_LAST_INGEST_KEY_PREFIX}{query.lower().replace(' ', '_')}"
    await redis_client.set(key, datetime.now(timezone.utc).isoformat())


async def _light_ingest(source: str, query: str) -> None:
    """Fire-and-forget light ingestion (max 20 results)."""
    try:
        import httpx
        endpoint_map = {
            "clinicaltrials": f"http://localhost:8000/ingest/trials?query={query}&max_results=20",
            "pubmed": f"http://localhost:8000/ingest/pubmed?query={query}&max_results=20",
            "biorxiv": f"http://localhost:8000/ingest/biorxiv?query={query}&days=30&max_results=20",
            "ema": "http://localhost:8000/ingest/ema",
        }
        url = endpoint_map.get(source)
        if not url:
            return
        async with httpx.AsyncClient(timeout=120.0) as client:
            await client.post(url)
        logger.info(f"[Researcher] light ingest done: source={source} query={query!r}")
    except Exception as e:
        logger.warning(f"[Researcher] light ingest failed: {e}")


async def _search_target(target: dict) -> dict:
    query = target.get("query", "")
    source = target.get("source", "papers")
    rag_source = _SOURCE_TO_RAG.get(source, "papers")

    try:
        hits = await rag_service.retrieve(query=query, sources=[rag_source], limit=5)
        return {
            "target": target,
            "hits": hits,
            "source": source,
            "query": query,
        }
    except Exception as e:
        logger.warning(f"[Researcher] search error for {query!r}: {e}")
        return {"target": target, "hits": [], "source": source, "query": query, "error": str(e)}


async def researcher_node(state: SynState) -> dict:
    t0 = time.monotonic()
    targets = state.get("targets") or []
    logger.info(f"[Researcher] start — {len(targets)} targets")

    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        # Check stale ingestions and trigger light ingest in background
        ingest_tasks = []
        for target in targets:
            query = target.get("query", "")
            source = target.get("source", "")
            hours = await _last_ingestion_hours(redis_client, query)
            if hours > _INGESTION_TTL_HOURS:
                logger.info(f"[Researcher] triggering light ingest: {source}/{query!r}")
                ingest_tasks.append(asyncio.create_task(_light_ingest(source, query)))
                await _mark_ingested(redis_client, query)

        # Semantic search in Qdrant for all targets in parallel
        search_results = await asyncio.gather(*[_search_target(t) for t in targets])

        raw_results = []
        sources_searched = []
        for result in search_results:
            raw_results.append(result)
            sources_searched.append(f"{result['source']}:{result['query']}")

        logger.info(
            f"[Researcher] done in {time.monotonic()-t0:.1f}s — "
            f"{len(raw_results)} groups, {sum(len(r['hits']) for r in raw_results)} hits"
        )
        return {
            "raw_results": raw_results,
            "sources_searched": sources_searched,
            "current_agent": "analyzer",
            "status": "analyzing",
        }
    except Exception as e:
        logger.error(f"[Researcher] error: {e}")
        return {
            "raw_results": [],
            "sources_searched": [],
            "current_agent": "analyzer",
            "status": "analyzing",
            "errors": [f"researcher: {e}"],
        }
    finally:
        await redis_client.aclose()
