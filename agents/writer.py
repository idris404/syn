import time
from datetime import datetime

from groq import AsyncGroq
from loguru import logger

from agents.state import SynState
from app.config import settings

_WRITER_SYSTEM = (
    "Tu es un rédacteur expert en veille stratégique R&D pharma/biotech. "
    "Tu rédiges des rapports clairs, structurés et professionnels en Markdown."
)

_REPORT_TEMPLATE = """\
# {titre} — Veille R&D {date}

## Résumé exécutif

{executive_summary}

## Findings clés

{key_findings_section}

## Analyse détaillée

{analysis}

## Mises à jour concurrentes

{competitor_updates_section}

## Sources

{sources_section}

---

_Rapport généré automatiquement par SYN le {datetime}_
"""


def _format_findings(key_findings: list[dict]) -> str:
    if not key_findings:
        return "_Aucun finding identifié._"
    lines = []
    emoji_map = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    for i, f in enumerate(key_findings, 1):
        importance = f.get("importance", "medium")
        icon = emoji_map.get(importance, "•")
        lines.append(f"{i}. {icon} **{f.get('finding', '')}**")
        if f.get("evidence"):
            lines.append(f"   _Evidence : {f['evidence']}_")
    return "\n".join(lines)


def _format_competitors(competitor_updates: list[dict]) -> str:
    if not competitor_updates:
        return "_Aucune mise à jour concurrente notable._"
    lines = []
    for c in competitor_updates:
        company = c.get("company", "?")
        update = c.get("update", "")
        source = c.get("source", "")
        line = f"- **{company}** : {update}"
        if source:
            line += f" _(source: {source})_"
        lines.append(line)
    return "\n".join(lines)


def _format_sources(sources_searched: list[str]) -> str:
    if not sources_searched:
        return "_Sources non disponibles._"
    return "\n".join(f"- {s}" for s in sources_searched)


def _fallback_report(state: SynState) -> dict:
    now = datetime.utcnow()
    date_str = now.strftime("%d/%m/%Y")
    title = f"Veille R&D SYN — {date_str}"
    analysis = state.get("analysis") or "Analyse indisponible."
    key_findings = state.get("key_findings") or []
    competitor_updates = state.get("competitor_updates") or []
    sources_searched = state.get("sources_searched") or []

    body = _REPORT_TEMPLATE.format(
        titre="Rapport de Veille",
        date=date_str,
        executive_summary="Rapport généré en mode dégradé (erreur rédaction LLM).",
        key_findings_section=_format_findings(key_findings),
        analysis=analysis,
        competitor_updates_section=_format_competitors(competitor_updates),
        sources_section=_format_sources(sources_searched),
        datetime=now.strftime("%d/%m/%Y %H:%M UTC"),
    )
    summary = f"Rapport de veille SYN du {date_str}. {len(key_findings)} finding(s) identifié(s)."
    return {"report_title": title, "report_body": body, "report_summary": summary}


async def writer_node(state: SynState) -> dict:
    t0 = time.monotonic()
    analysis = state.get("analysis") or ""
    key_findings = state.get("key_findings") or []
    competitor_updates = state.get("competitor_updates") or []
    sources_searched = state.get("sources_searched") or []
    logger.info(f"[Writer] start — {len(key_findings)} findings")

    try:
        now = datetime.utcnow()
        date_str = now.strftime("%d/%m/%Y")

        if not settings.groq_api_key:
            result = _fallback_report(state)
            return {**result, "current_agent": "publisher", "status": "publishing"}

        user_prompt = (
            f"Date : {date_str}\n"
            f"Analyse : {analysis[:1500]}\n"
            f"Findings clés (JSON) : {key_findings}\n"
            f"Mises à jour concurrentes (JSON) : {competitor_updates}\n\n"
            "Génère un titre percutant (max 10 mots) et un résumé exécutif en 2-3 phrases. "
            "Réponds JSON : {\"title\": \"...\", \"executive_summary\": \"...\", \"discord_summary\": \"...\"}"
        )

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _WRITER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        import json
        parsed = json.loads(response.choices[0].message.content or "{}")
        title = parsed.get("title", f"Veille R&D SYN — {date_str}")
        executive_summary = parsed.get("executive_summary", "")
        discord_summary = parsed.get("discord_summary", executive_summary)

        body = _REPORT_TEMPLATE.format(
            titre=title,
            date=date_str,
            executive_summary=executive_summary,
            key_findings_section=_format_findings(key_findings),
            analysis=analysis,
            competitor_updates_section=_format_competitors(competitor_updates),
            sources_section=_format_sources(sources_searched),
            datetime=now.strftime("%d/%m/%Y %H:%M UTC"),
        )

        logger.info(f"[Writer] done in {time.monotonic()-t0:.1f}s — title={title!r}")
        return {
            "report_title": title,
            "report_body": body,
            "report_summary": discord_summary,
            "current_agent": "publisher",
            "status": "publishing",
        }
    except Exception as e:
        logger.error(f"[Writer] error: {e}")
        result = _fallback_report(state)
        return {
            **result,
            "current_agent": "publisher",
            "status": "publishing",
            "errors": [f"writer: {e}"],
        }
