import json
import time

from groq import AsyncGroq
from loguru import logger

from agents.state import SynState
from app.config import settings

_ANALYZER_PROMPT = """\
Tu es un analyste senior R&D pharma/biotech.
Analyse les données suivantes et identifie les points clés.

Données collectées : {raw_results_summary}
Contexte documentaire : {rag_context}
{visual_context}
Produis :
1. Une analyse synthétique (3-4 paragraphes)
2. Les findings clés (max 5) avec niveau d'importance
3. Les mises à jour concurrentes notables

Réponds UNIQUEMENT en JSON valide :
{{
  "analysis": "...",
  "key_findings": [{{"finding": "...", "evidence": "...", "importance": "high|medium|low"}}],
  "competitor_updates": [{{"company": "...", "update": "...", "source": "..."}}]
}}
"""

_FALLBACK_ANALYSIS = {
    "analysis": "Analyse indisponible — aucune donnée suffisante ou erreur LLM.",
    "key_findings": [],
    "competitor_updates": [],
}


def _summarize_results(raw_results: list[dict]) -> str:
    lines = []
    for group in raw_results[:5]:
        query = group.get("query", "?")
        source = group.get("source", "?")
        hits = group.get("hits", [])
        lines.append(f"Source: {source} | Query: {query!r} | Résultats: {len(hits)}")
        for hit in hits[:3]:
            title = hit.get("title", "sans titre")
            score = hit.get("score")
            score_str = f" (score={score:.3f})" if score else ""
            lines.append(f"  - {title}{score_str}")
    return "\n".join(lines) if lines else "Aucun résultat."


def _build_rag_context(raw_results: list[dict]) -> str:
    snippets = []
    for group in raw_results:
        for hit in group.get("hits", [])[:2]:
            title = hit.get("title", "")
            abstract = (hit.get("abstract") or hit.get("text") or "")[:400]
            if title or abstract:
                snippets.append(f"[{title}]\n{abstract}")
    return "\n\n".join(snippets[:8]) if snippets else "Pas de contexte disponible."


async def _build_visual_context(targets: list[dict]) -> str:
    """Retrieve visual findings from syn_figures and format them for the prompt."""
    if not targets:
        return ""
    try:
        from app.services import qdrant_service
        query = targets[0].get("query", "") if targets else ""
        if not query:
            return ""
        visual_findings = await qdrant_service.search_figures(query=query, limit=5)
        if not visual_findings:
            return ""

        lines = ["\nDonnées visuelles extraites (courbes, forest plots, tableaux) :"]
        for fig in visual_findings:
            payload = fig.get("payload", {})
            fig_type = payload.get("figure_type", "figure")
            hr = payload.get("hr")
            p_value = payload.get("p_value")
            endpoint = payload.get("endpoint", "")
            interp = fig.get("raw_interpretation", "")[:200]

            line = f"- [{fig_type}]"
            if endpoint:
                line += f" endpoint={endpoint}"
            if hr is not None:
                line += f" HR={hr}"
            if p_value is not None:
                line += f" p={p_value}"
            line += f" — {interp}"
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[Analyzer] visual context fetch error: {e}")
        return ""


async def analyzer_node(state: SynState) -> dict:
    t0 = time.monotonic()
    raw_results = state.get("raw_results") or []
    targets = state.get("targets") or []
    logger.info(f"[Analyzer] start — {len(raw_results)} result groups")

    try:
        if not settings.groq_api_key:
            logger.warning("[Analyzer] No GROQ_API_KEY — returning fallback analysis")
            return {
                **_FALLBACK_ANALYSIS,
                "current_agent": "writer",
                "status": "writing",
            }

        raw_summary = _summarize_results(raw_results)
        rag_ctx = _build_rag_context(raw_results)
        visual_ctx = await _build_visual_context(targets)

        if visual_ctx:
            logger.info(f"[Analyzer] visual context: {len(visual_ctx)} chars")

        prompt = _ANALYZER_PROMPT.format(
            raw_results_summary=raw_summary,
            rag_context=rag_ctx,
            visual_context=visual_ctx,
        )

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_json = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_json)

        logger.info(
            f"[Analyzer] done in {time.monotonic()-t0:.1f}s — "
            f"{len(parsed.get('key_findings', []))} findings"
            + (f" + visual data" if visual_ctx else "")
        )
        return {
            "analysis": parsed.get("analysis", ""),
            "key_findings": parsed.get("key_findings", [])[:5],
            "competitor_updates": parsed.get("competitor_updates", []),
            "current_agent": "writer",
            "status": "writing",
        }
    except Exception as e:
        logger.error(f"[Analyzer] error: {e}")
        return {
            "analysis": f"Erreur d'analyse: {e}",
            "key_findings": [],
            "competitor_updates": [],
            "current_agent": "writer",
            "status": "writing",
            "errors": [f"analyzer: {e}"],
        }
