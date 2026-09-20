from fastapi import APIRouter, HTTPException

from app.schemas.trial import RAGQuery, RAGResponse, RAGSourceUsed
from app.services import rag_service

router = APIRouter(prefix="/rag", tags=["rag"])

_DEFAULT_MODEL = "llama-3.3-70b-versatile"


@router.post("/query", response_model=RAGResponse)
async def rag_query(body: RAGQuery) -> RAGResponse:
    try:
        context = await rag_service.retrieve(
            query=body.question,
            sources=body.sources,
            limit=body.limit,
        )
    except rag_service.RetrievalUnavailable:
        raise HTTPException(status_code=503, detail="Vector search is unavailable") from None

    answer, tokens = await rag_service.generate(
        query=body.question,
        context=context,
        model=_DEFAULT_MODEL,
    )

    sources_used = [
        RAGSourceUsed(
            nct_id=hit.get("nct_id"),
            external_id=hit.get("nct_id") or hit.get("pmid") or hit.get("doi") or hit.get("product_number") or hit.get("upload_id"),
            url=hit.get("url") or (f"https://clinicaltrials.gov/study/{hit['nct_id']}" if hit.get("nct_id") else None),
            title=hit.get("title"),
            score=hit.get("score"),
            source=hit.get("source") or hit.get("_source_name"),
        )
        for hit in context
    ]

    return RAGResponse(
        question=body.question,
        answer=answer,
        sources_used=sources_used,
        model=_DEFAULT_MODEL,
        tokens_used=tokens,
    )
