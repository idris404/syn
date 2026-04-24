from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.trial import TrialResponse, TrialSearchResponse
from app.services import trial_service

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


@router.get("/{nct_id}", response_model=TrialResponse)
async def get_trial(
    nct_id: str,
    session: AsyncSession = Depends(get_session),
) -> TrialResponse:
    trial = await trial_service.get_by_nct_id(session, nct_id)
    if trial is None:
        raise HTTPException(status_code=404, detail=f"Trial {nct_id} not found")
    return trial
