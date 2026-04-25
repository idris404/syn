from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.figure import FigureRecord
from app.schemas.figure import FigureResponse

router = APIRouter(prefix="/papers", tags=["figures"])


@router.get("/{upload_id}/figures", response_model=list[FigureResponse])
async def get_figures(
    upload_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[FigureResponse]:
    """Return all figures extracted from a PDF, ordered by page + figure_index."""
    stmt = (
        select(FigureRecord)
        .where(FigureRecord.upload_id == upload_id)
        .order_by(FigureRecord.page_number, FigureRecord.figure_index)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    if not records:
        raise HTTPException(status_code=404, detail=f"No figures found for upload_id={upload_id}")

    return [
        FigureResponse(
            id=str(r.id),
            upload_id=r.upload_id,
            paper_nct_id=r.paper_nct_id,
            page_number=r.page_number,
            figure_index=r.figure_index,
            figure_type=r.figure_type,
            raw_interpretation=r.raw_interpretation,
            structured_data=r.structured_data or {},
            confidence_score=r.confidence_score,
            qdrant_id=str(r.qdrant_id) if r.qdrant_id else None,
            created_at=r.created_at,
        )
        for r in records
    ]
