import uuid
from functools import lru_cache

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


async def ensure_collections() -> None:
    client = get_qdrant_client()
    collections = (
        settings.qdrant_trials_collection,
        settings.qdrant_papers_collection,
        settings.qdrant_ema_collection,
        settings.qdrant_figures_collection,
    )
    for collection_name in collections:
        exists = await client.collection_exists(collection_name)
        if not exists:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {collection_name}")
        else:
            logger.info(f"Qdrant collection already exists: {collection_name}")


async def upsert_trial(
    qdrant_id: uuid.UUID,
    vector: list[float],
    nct_id: str,
    title: str | None,
    status: str | None,
    phase: str | None,
    sponsor: str | None,
) -> None:
    client = get_qdrant_client()
    point = PointStruct(
        id=str(qdrant_id),
        vector=vector,
        payload={
            "nct_id": nct_id,
            "title": title,
            "status": status,
            "phase": phase,
            "sponsor": sponsor,
        },
    )
    await client.upsert(collection_name=settings.qdrant_trials_collection, points=[point])


async def search_trials(vector: list[float], limit: int = 20) -> list[tuple[str, float]]:
    client = get_qdrant_client()
    results = await client.search(
        collection_name=settings.qdrant_trials_collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
    )
    return [(hit.payload["nct_id"], hit.score) for hit in results]


async def upsert_paper(
    paper_id: str,
    vector: list[float],
    payload: dict,
    collection: str | None = None,
) -> None:
    client = get_qdrant_client()
    col = collection or settings.qdrant_papers_collection
    point = PointStruct(id=paper_id, vector=vector, payload=payload)
    await client.upsert(collection_name=col, points=[point])


async def search_papers(
    vector: list[float],
    limit: int = 20,
    source_filter: str | None = None,
    collection: str | None = None,
) -> list[dict]:
    client = get_qdrant_client()
    col = collection or settings.qdrant_papers_collection

    query_filter = None
    if source_filter:
        query_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=source_filter))]
        )

    results = await client.search(
        collection_name=col,
        query_vector=vector,
        limit=limit,
        with_payload=True,
        query_filter=query_filter,
    )
    hits = []
    for hit in results:
        hits.append({"score": hit.score, **hit.payload})
    return hits


async def search_papers_by_payload(
    key: str,
    value: str,
    collection: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Scroll/filter by payload field (no vector needed)."""
    client = get_qdrant_client()
    col = collection or settings.qdrant_papers_collection
    results, _ = await client.scroll(
        collection_name=col,
        scroll_filter=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))]),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [{"score": None, **r.payload} for r in results]


# ── Figures (Phase 3) ──────────────────────────────────────────────────────

async def upsert_figure(
    figure_id: str,
    vector: list[float],
    payload: dict,
) -> None:
    """Upsert a figure interpretation into syn_figures collection."""
    client = get_qdrant_client()
    point = PointStruct(id=figure_id, vector=vector, payload=payload)
    await client.upsert(collection_name=settings.qdrant_figures_collection, points=[point])


async def search_figures(
    query: str,
    limit: int = 5,
    figure_type_filter: str | None = None,
) -> list[dict]:
    """Semantic search on figure interpretations."""
    from app.services.trial_service import get_embedding_model
    model = get_embedding_model()
    vector = model.encode(query).tolist()

    client = get_qdrant_client()
    query_filter = None
    if figure_type_filter:
        query_filter = Filter(
            must=[FieldCondition(key="figure_type", match=MatchValue(value=figure_type_filter))]
        )

    results = await client.search(
        collection_name=settings.qdrant_figures_collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
        query_filter=query_filter,
    )
    return [{"score": hit.score, "payload": hit.payload, "raw_interpretation": hit.payload.get("raw_interpretation", "")} for hit in results]


async def get_figures_by_upload_id(upload_id: str, limit: int = 50) -> list[dict]:
    """Scroll figures by upload_id payload field."""
    client = get_qdrant_client()
    try:
        results, _ = await client.scroll(
            collection_name=settings.qdrant_figures_collection,
            scroll_filter=Filter(must=[FieldCondition(key="upload_id", match=MatchValue(value=upload_id))]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [{"score": None, **r.payload} for r in results]
    except Exception as e:
        logger.warning(f"get_figures_by_upload_id error: {e}")
        return []
