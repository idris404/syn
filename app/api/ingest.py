import time

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.ingestion import clinical_trials, pubmed
from app.schemas.trial import IngestReport
from app.services import qdrant_service, trial_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/trials", response_model=IngestReport)
async def ingest_trials(
    query: str = Query(..., description="Search term for ClinicalTrials.gov"),
    max_results: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> IngestReport:
    start = time.monotonic()
    total_fetched = inserted = updated = skipped = errors = 0

    async for trial in clinical_trials.fetch_trials(query, max_results):
        total_fetched += 1
        try:
            nct_id, was_inserted = await trial_service.upsert_trial(session, trial)
            if was_inserted:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            logger.error(f"Error upserting trial {trial.nct_id}: {e}")
            errors += 1

    duration = round(time.monotonic() - start, 2)
    logger.info(
        f"Ingest trials '{query}': fetched={total_fetched} inserted={inserted} "
        f"updated={updated} errors={errors} duration={duration}s"
    )
    return IngestReport(
        query=query,
        total_fetched=total_fetched,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors,
        duration_seconds=duration,
    )


@router.post("/pubmed")
async def ingest_pubmed(
    query: str = Query(..., description="Search term for PubMed"),
    max_results: int = Query(50, ge=1, le=500),
) -> dict:
    start = time.monotonic()
    total_fetched = errors = 0

    async for paper in pubmed.fetch_papers(query, max_results):
        total_fetched += 1
        try:
            embedding_text = f"{paper['title']} | {paper['abstract']}"
            model = trial_service.get_embedding_model()
            vector = model.encode(embedding_text).tolist()
            await qdrant_service.upsert_paper(
                pmid=paper["pmid"],
                vector=vector,
                title=paper["title"],
                journal=paper["journal"],
                year=paper["year"],
                mesh_terms=paper["mesh_terms"],
            )
        except Exception as e:
            logger.error(f"Error upserting paper {paper.get('pmid')}: {e}")
            errors += 1

    duration = round(time.monotonic() - start, 2)
    return {
        "query": query,
        "total_fetched": total_fetched,
        "errors": errors,
        "duration_seconds": duration,
    }
