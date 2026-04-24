from loguru import logger

from app.config import settings
from app.services import qdrant_service
from app.services.trial_service import get_embedding_model

SYSTEM_PROMPT = (
    "Tu es un analyste senior en veille R&D pharma/biotech. "
    "Tu réponds uniquement en te basant sur les données fournies dans le contexte. "
    "Si l'information n'est pas dans le contexte, dis-le clairement. "
    "Format de réponse : 2-3 paragraphes structurés, langage professionnel."
)

_COLLECTION_MAP = {
    "trials": settings.qdrant_trials_collection,
    "papers": settings.qdrant_papers_collection,
    "ema": settings.qdrant_ema_collection,
}


async def retrieve(
    query: str,
    sources: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    model = get_embedding_model()
    vector = model.encode(query).tolist()

    if sources is None:
        collections = list(_COLLECTION_MAP.items())
    else:
        collections = [(s, _COLLECTION_MAP[s]) for s in sources if s in _COLLECTION_MAP]

    all_hits: list[dict] = []

    for source_name, collection in collections:
        try:
            hits = await qdrant_service.search_papers(
                vector=vector,
                limit=limit,
                collection=collection,
            )
            for hit in hits:
                hit["_source_name"] = source_name
                all_hits.append(hit)
        except Exception as e:
            logger.warning(f"RAG retrieve error for {source_name}: {e}")

    # Re-rank by score descending, return top limit
    all_hits.sort(key=lambda h: h.get("score") or 0, reverse=True)
    return all_hits[:limit]


async def generate(
    query: str,
    context: list[dict],
    model: str = "llama-3.3-70b-versatile",
) -> tuple[str, int | None]:
    """Returns (answer_text, tokens_used)."""
    from groq import AsyncGroq

    if not settings.groq_api_key:
        return (
            "GROQ_API_KEY non configuré. Ajoutez votre clé dans .env pour activer la génération LLM.",
            None,
        )

    context_text = "\n\n".join(
        f"[Source {i+1} — score={hit.get('score', 'N/A'):.3f}]\n"
        f"Titre: {hit.get('title', 'N/A')}\n"
        f"{hit.get('abstract', hit.get('text', ''))[:600]}"
        for i, hit in enumerate(context)
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Contexte:\n{context_text}\n\nQuestion: {query}",
        },
    ]

    client = AsyncGroq(api_key=settings.groq_api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1024,
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else None
    return answer, tokens
