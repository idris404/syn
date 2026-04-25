import time
import uuid as uuid_lib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.ingestion import biorxiv, clinical_trials, ema, pdf_parser, pubmed
from app.schemas.trial import IngestReport, PDFUploadResponse
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
            paper_id = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_URL, f"pmid:{paper['pmid']}"))
            await qdrant_service.upsert_paper(
                paper_id=paper_id,
                vector=vector,
                payload={
                    "source": "pubmed",
                    "pmid": paper["pmid"],
                    "title": paper["title"],
                    "abstract": (paper.get("abstract") or "")[:500],
                    "journal": paper["journal"],
                    "year": paper["year"],
                    "mesh_terms": paper["mesh_terms"],
                    "authors": [],
                },
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


@router.post("/biorxiv")
async def ingest_biorxiv(
    query: str = Query(..., description="Keyword filter"),
    days: int = Query(30, ge=1, le=365),
    max_results: int = Query(100, ge=1, le=500),
) -> dict:
    start = time.monotonic()
    total_fetched = errors = 0

    async for paper in biorxiv.fetch_papers(query=query, days=days, max_results=max_results):
        total_fetched += 1
        try:
            embedding_text = f"{paper['title']} {paper['abstract']}"
            model = trial_service.get_embedding_model()
            vector = model.encode(embedding_text).tolist()
            await qdrant_service.upsert_paper(
                paper_id=paper["id"],
                vector=vector,
                payload={
                    "source": "biorxiv",
                    "doi": paper["doi"],
                    "title": paper["title"],
                    "abstract": paper["abstract"][:500],
                    "category": paper["category"],
                    "date": paper["date"],
                    "authors": paper["authors"],
                    "server": paper["server"],
                    "version": paper["version"],
                },
            )
        except Exception as e:
            logger.error(f"Error upserting biorxiv paper {paper.get('doi')}: {e}")
            errors += 1

    duration = round(time.monotonic() - start, 2)
    logger.info(f"Ingest bioRxiv '{query}': fetched={total_fetched} errors={errors} duration={duration}s")
    return {
        "query": query,
        "days": days,
        "total_fetched": total_fetched,
        "errors": errors,
        "duration_seconds": duration,
    }


@router.post("/ema")
async def ingest_ema() -> dict:
    start = time.monotonic()
    total_fetched = errors = 0

    async for medicine in ema.fetch_medicines():
        total_fetched += 1
        try:
            embedding_text = (
                f"{medicine['medicine_name']} {medicine['active_substance']} {medicine['inn']}"
            )
            model = trial_service.get_embedding_model()
            vector = model.encode(embedding_text).tolist()
            await qdrant_service.upsert_paper(
                paper_id=medicine["id"],
                vector=vector,
                payload={
                    "source": "ema",
                    "product_number": medicine["product_number"],
                    "medicine_name": medicine["medicine_name"],
                    "active_substance": medicine["active_substance"],
                    "inn": medicine["inn"],
                    "atc_code": medicine["atc_code"],
                    "authorisation_status": medicine["authorisation_status"],
                    "category": medicine["category"],
                    "orphan_medicine": medicine["orphan_medicine"],
                    "first_published": medicine["first_published"],
                    "revision_date": medicine["revision_date"],
                    "url": medicine["url"],
                    "title": medicine["medicine_name"],
                },
                collection=settings.qdrant_ema_collection,
            )
        except Exception as e:
            logger.error(f"Error upserting EMA medicine {medicine.get('product_number')}: {e}")
            errors += 1

    duration = round(time.monotonic() - start, 2)
    logger.info(f"Ingest EMA: total={total_fetched} errors={errors} duration={duration}s")
    return {
        "total_fetched": total_fetched,
        "errors": errors,
        "duration_seconds": duration,
    }


@router.post("/pdf", response_model=PDFUploadResponse)
async def ingest_pdf(
    file: UploadFile = File(...),
    title: str | None = Query(None),
    source_type: str = Query("paper", description="trial_result|paper|report"),
) -> PDFUploadResponse:
    start = time.monotonic()

    if file.size and file.size > 50 * 1024 * 1024:
        from fastapi import HTTPException
        raise HTTPException(status_code=413, detail="PDF too large (max 50MB)")

    upload_id = str(uuid_lib.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "upload.pdf"

    chunks = pdf_parser.parse_pdf(file_bytes=file_bytes, filename=filename, upload_id=upload_id)
    pages = len(pdf_parser.doc_pages(file_bytes))

    model = trial_service.get_embedding_model()
    errors = 0

    for chunk in chunks:
        try:
            chunk_uuid = pdf_parser.chunk_id(filename, chunk.chunk_index)
            vector = model.encode(chunk.text).tolist()
            await qdrant_service.upsert_paper(
                paper_id=chunk_uuid,
                vector=vector,
                payload={
                    "source": "pdf",
                    "filename": filename,
                    "title": title or filename,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    "section": chunk.section,
                    "total_chunks": chunk.total_chunks,
                    "upload_id": upload_id,
                    "source_type": source_type,
                    "abstract": chunk.text[:500],
                },
            )
        except Exception as e:
            logger.error(f"Error upserting PDF chunk {chunk.chunk_index}: {e}")
            errors += 1

    duration = round(time.monotonic() - start, 2)
    logger.info(
        f"PDF ingest: {filename} pages={pages} chunks={len(chunks)} errors={errors} duration={duration}s"
    )
    return PDFUploadResponse(
        filename=filename,
        pages=pages,
        chunks_created=len(chunks) - errors,
        upload_id=upload_id,
        duration_seconds=duration,
    )


@router.post("/pdf/vision")
async def ingest_pdf_vision(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    nct_id: str = Form(default=""),
    db: AsyncSession = Depends(get_session),
):
    """
    Upload PDF → Vision LLM figure extraction → Qdrant syn_figures + PostgreSQL figure_records.
    Requires ANTHROPIC_API_KEY or OPENAI_API_KEY in .env.
    """
    from app.ingestion import vision_parser
    from app.models.figure import FigureRecord
    from app.schemas.figure import FigureSummary, VisionIngestResponse

    if not settings.anthropic_api_key and not settings.openai_api_key:
        raise HTTPException(
            status_code=422,
            detail="Vision API not configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env",
        )

    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF too large (max 50MB)")

    start = time.monotonic()
    upload_id = str(uuid_lib.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "upload.pdf"

    logger.info(f"[Vision] pipeline start: filename={filename} upload_id={upload_id}")

    all_pages, interpretations = await vision_parser.run_vision_pipeline(
        file_bytes=file_bytes,
        upload_id=upload_id,
    )

    embedding_model = trial_service.get_embedding_model()
    figures_summary: list = []

    for interp in interpretations:
        fig_id = vision_parser.figure_uuid(upload_id, interp.page_num, interp.figure_index)
        sd = interp.structured_data or {}
        hr_val = sd.get("hazard_ratio") or sd.get("hr")
        p_val = sd.get("p_value")
        endpoint = sd.get("endpoint", "")

        qdrant_payload = {
            "upload_id": upload_id,
            "figure_type": interp.figure_type,
            "confidence": interp.confidence,
            "paper_nct_id": nct_id or None,
            "page_number": interp.page_num,
            "raw_interpretation": interp.raw_interpretation,
            "endpoint": endpoint,
            "hr": float(hr_val) if hr_val is not None else None,
            "p_value": float(p_val) if p_val is not None else None,
        }

        try:
            vector = embedding_model.encode(interp.raw_interpretation[:1000]).tolist()
            await qdrant_service.upsert_figure(
                figure_id=fig_id,
                vector=vector,
                payload=qdrant_payload,
            )
        except Exception as e:
            logger.error(f"[Vision] Qdrant upsert error: {e}")

        thumb_b64 = interp.image_base64[:65000] if interp.image_base64 else None
        fig_uuid = uuid_lib.UUID(fig_id)
        record = FigureRecord(
            id=fig_uuid,
            upload_id=upload_id,
            paper_nct_id=nct_id or None,
            page_number=interp.page_num,
            figure_index=interp.figure_index,
            figure_type=interp.figure_type,
            raw_interpretation=interp.raw_interpretation,
            structured_data=interp.structured_data,
            confidence_score=interp.confidence,
            image_base64=thumb_b64,
            qdrant_id=fig_uuid,
        )
        db.add(record)

        figures_summary.append({
            "page": interp.page_num,
            "figure_index": interp.figure_index,
            "figure_type": interp.figure_type,
            "confidence": interp.confidence,
            "summary": interp.raw_interpretation[:200],
            "figure_id": fig_id,
        })

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"[Vision] DB commit error: {e}")

    duration = round(time.monotonic() - start, 2)
    provider = settings.vision_provider if settings.anthropic_api_key or settings.openai_api_key else "none"
    logger.info(
        f"[Vision] done: {filename} pages={len(all_pages)} "
        f"figures={len(interpretations)} duration={duration}s"
    )
    return {
        "upload_id": upload_id,
        "filename": filename,
        "pages_analyzed": len(all_pages),
        "figures_found": len(interpretations),
        "figures": figures_summary,
        "duration_seconds": duration,
        "vision_provider": provider,
    }
