from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.trial import PaperResponse, TrialResponse, TrialSearchResponse
from app.services import qdrant_service, trial_service
from app.services.trial_service import get_embedding_model

router = APIRouter(prefix="/trials", tags=["trials"])


@router.get("/search", response_model=TrialSearchResponse)
async def search_trials(
    q: str = Query(..., description="Semantic search query"),
    phase: str | None = Query(None, description="Filter by phase (e.g. PHASE3)"),
    status: str | None = Query(None, description="Filter by status (e.g. RECRUITING)"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> TrialSearchResponse:
    results = await trial_service.search_trials_hybrid(
        session=session, query=q, phase=phase, status=status, limit=limit
    )
    return TrialSearchResponse(query=q, count=len(results), results=results)


@router.get("/{nct_id}/papers", response_model=list[PaperResponse])
async def get_trial_papers(
    nct_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[PaperResponse]:
    # 1. Search by payload field nct_ids_mentioned
    payload_hits = await qdrant_service.search_papers_by_payload(
        key="nct_ids_mentioned",
        value=nct_id,
        limit=10,
    )

    # 2. Semantic search using trial title
    trial = await trial_service.get_by_nct_id(session, nct_id)
    semantic_hits: list[dict] = []
    if trial and trial.title:
        model = get_embedding_model()
        vector = model.encode(trial.title).tolist()
        semantic_hits = await qdrant_service.search_papers(vector=vector, limit=10)

    # Merge, deduplicate by doi/pmid
    seen: set[str] = set()
    merged: list[dict] = []
    for hit in payload_hits + semantic_hits:
        key = hit.get("doi") or hit.get("pmid") or hit.get("title") or ""
        if key and key not in seen:
            seen.add(key)
            merged.append(hit)

    merged = merged[:10]

    return [
        PaperResponse(
            id=hit.get("doi") or hit.get("pmid") or hit.get("product_number") or "",
            source=hit.get("source", "unknown"),
            title=hit.get("title"),
            abstract=(hit.get("abstract") or "")[:300] or None,
            score=hit.get("score"),
            external_id=hit.get("doi") or hit.get("pmid") or hit.get("product_number"),
            date=hit.get("date") or hit.get("year"),
            authors=hit.get("authors") or [],
            url=hit.get("url"),
        )
        for hit in merged
    ]


@router.get("/{nct_id}", response_model=TrialResponse)
async def get_trial(
    nct_id: str,
    session: AsyncSession = Depends(get_session),
) -> TrialResponse:
    trial = await trial_service.get_by_nct_id(session, nct_id)
    if trial is None:
        raise HTTPException(status_code=404, detail=f"Trial {nct_id} not found")
    return trial
