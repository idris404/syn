import json
import time
from datetime import date

from groq import AsyncGroq
from loguru import logger

from agents.state import SynState
from app.config import settings

_REDIS_HISTORY_KEY = "syn:runs:history"

_PLANNER_PROMPT = """\
Tu es un analyste R&D pharma/biotech. Tu dois décider quoi surveiller
aujourd'hui dans le pipeline de veille compétitive.

Derniers runs : {recent_runs}
Date du jour : {today}

Génère une liste de 3 à 5 cibles de recherche prioritaires.
Pour chaque cible, spécifie :
- query : terme de recherche précis
- source : "clinicaltrials" | "pubmed" | "biorxiv" | "ema"
- priority : "high" | "medium" | "low"
- reason : pourquoi c'est pertinent maintenant (1 phrase)

Réponds UNIQUEMENT en JSON valide :
{"targets": [...], "reasoning": "..."}
"""

_FALLBACK_TARGETS = [
    {"query": "oncology checkpoint inhibitor", "source": "clinicaltrials", "priority": "high", "reason": "Surveillance standard des essais oncologie."},
    {"query": "KRAS inhibitor phase 3", "source": "pubmed", "priority": "high", "reason": "Domaine d'intérêt R&D prioritaire."},
    {"query": "mRNA cancer vaccine", "source": "biorxiv", "priority": "medium", "reason": "Technologie émergente à surveiller."},
]


async def _get_recent_runs(redis_client) -> str:
    try:
        raw = await redis_client.get(_REDIS_HISTORY_KEY)
        if not raw:
            return "Aucun run précédent."
        history = json.loads(raw)
        last = history[-5:] if len(history) > 5 else history
        lines = [f"- {r.get('started_at','?')[:10]} | {r.get('status','?')} | {r.get('report_title','sans titre')}" for r in last]
        return "\n".join(lines) or "Aucun run précédent."
    except Exception as e:
        logger.warning(f"Planner: Redis history fetch error: {e}")
        return "Historique indisponible."


async def planner_node(state: SynState) -> dict:
    t0 = time.monotonic()
    logger.info(f"[Planner] start run_id={state['run_id']}")

    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        recent_runs = await _get_recent_runs(redis_client)
        today = date.today().isoformat()

        prompt = _PLANNER_PROMPT.format(recent_runs=recent_runs, today=today)

        if not settings.groq_api_key:
            logger.warning("[Planner] No GROQ_API_KEY — using fallback targets")
            targets = _FALLBACK_TARGETS
            reasoning = "Fallback: clé Groq manquante."
        else:
            client = AsyncGroq(api_key=settings.groq_api_key)
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            raw_json = response.choices[0].message.content or "{}"
            parsed = json.loads(raw_json)
            # Normalize keys — Groq sometimes returns keys with escaped quotes
            parsed = {k.strip('"'): v for k, v in parsed.items()}
            targets = parsed.get("targets") or _FALLBACK_TARGETS
            targets = targets[:5]
            reasoning = parsed.get("reasoning", "")

        logger.info(f"[Planner] done in {time.monotonic()-t0:.1f}s — {len(targets)} targets")
        return {
            "targets": targets,
            "plan_reasoning": reasoning,
            "current_agent": "researcher",
            "status": "researching",
        }
    except Exception as e:
        logger.error(f"[Planner] error: {e}")
        return {
            "targets": _FALLBACK_TARGETS,
            "plan_reasoning": f"Erreur planner: {e}",
            "current_agent": "researcher",
            "status": "researching",
            "errors": [f"planner: {e}"],
        }
    finally:
        await redis_client.aclose()
