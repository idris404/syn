from fastapi import APIRouter, Query

from app.schemas.trial import PaperResponse
from app.services import qdrant_service
from app.services.trial_service import get_embedding_model

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("/search", response_model=list[PaperResponse])
async def search_papers(
    q: str = Query(..., description="Semantic search query"),
    source: str | None = Query(None, description="Filter by source: pubmed|biorxiv|pdf"),
    limit: int = Query(20, ge=1, le=100),
) -> list[PaperResponse]:
    model = get_embedding_model()
    vector = model.encode(q).tolist()
    hits = await qdrant_service.search_papers(vector=vector, limit=limit, source_filter=source)

    results = []
    for hit in hits:
        results.append(
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
        )
    return results
