import json
import re
import time
from datetime import datetime, timezone

import httpx
from loguru import logger

from agents.state import SynState
from app.api.ws import broadcast
from app.config import settings

_HISTORY_KEY = "syn:runs:history"
_ACTIVE_KEY = "syn:runs:active"
_MAX_HISTORY = 50


# ── Notion helpers ──────────────────────────────────────────────────────────

def _rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": content[:2000]}}]


def _paragraph_block(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _heading_block(level: int, text: str) -> dict:
    t = f"heading_{level}"
    return {"object": "block", "type": t, t: {"rich_text": _rich_text(text)}}


def _bullet_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    blocks: list[dict] = []
    for line in markdown.splitlines():
        if line.startswith("### "):
            blocks.append(_heading_block(3, line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(_heading_block(2, line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(_heading_block(1, line[2:].strip()))
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(_bullet_block(line[2:].strip()))
        elif line.strip() == "---":
            blocks.append(_divider_block())
        elif line.strip():
            # Strip inline bold (**text**) — keep text
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            blocks.append(_paragraph_block(clean.strip()))
    return blocks


async def _publish_notion(state: SynState) -> str | None:
    if not settings.notion_token or not settings.notion_reports_db_id:
        logger.warning("[Publisher] Notion not configured — skipping")
        return None

    today_iso = datetime.now(timezone.utc).date().isoformat()
    title = state.get("report_title") or "Rapport SYN"
    body = state.get("report_body") or ""
    sources_searched = state.get("sources_searched") or []

    # Build source multi_select (max 5)
    source_names = list({s.split(":")[0] for s in sources_searched})[:5]
    multi_select = [{"name": s} for s in source_names]

    blocks = markdown_to_notion_blocks(body)
    # Notion max 100 blocks per request — truncate
    blocks = blocks[:100]

    payload = {
        "parent": {"database_id": settings.notion_reports_db_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": today_iso}},
            "Status": {"select": {"name": "Published"}},
            "Sources": {"multi_select": multi_select},
        },
        "children": blocks,
    }

    headers = {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post("https://api.notion.com/v1/pages", json=payload, headers=headers)
        if resp.status_code in (200, 201):
            page_id = resp.json().get("id", "")
            notion_url = f"https://notion.so/{page_id.replace('-', '')}"
            logger.info(f"[Publisher] Notion page created: {notion_url}")
            return notion_url
        else:
            logger.error(f"[Publisher] Notion error {resp.status_code}: {resp.text[:300]}")
            return None


async def _send_discord(state: SynState, notion_url: str | None) -> None:
    if not settings.discord_webhook_url:
        logger.warning("[Publisher] Discord webhook not configured — skipping")
        return

    title = state.get("report_title") or "Rapport SYN"
    summary = state.get("report_summary") or ""
    key_findings = state.get("key_findings") or []
    sources_searched = state.get("sources_searched") or []
    now_iso = datetime.now(timezone.utc).isoformat()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    top_findings = "\n".join(
        f"• {f.get('finding', '')}" for f in key_findings[:3]
    ) or "_Aucun finding_"

    sources_str = f"{len(sources_searched)} source(s) consultée(s)"
    rapport_value = f"[Voir dans Notion]({notion_url})" if notion_url else "_Non publié_"

    embed = {
        "title": title,
        "description": summary[:400],
        "color": 0x00B4D8,
        "fields": [
            {"name": "Findings clés", "value": top_findings[:1024], "inline": False},
            {"name": "Sources", "value": sources_str, "inline": True},
            {"name": "Rapport complet", "value": rapport_value, "inline": True},
        ],
        "footer": {"text": f"SYN • {now_str}"},
        "timestamp": now_iso,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(settings.discord_webhook_url, json={"embeds": [embed]})
        if resp.status_code in (200, 204):
            logger.info("[Publisher] Discord alert sent")
        else:
            logger.error(f"[Publisher] Discord error {resp.status_code}: {resp.text[:200]}")


async def _save_to_redis(state: SynState, notion_url: str | None) -> None:
    import redis.asyncio as aioredis
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        run_id = state["run_id"]

        # Full state — force status to done
        state_copy = dict(state)
        state_copy["notion_url"] = notion_url
        state_copy["status"] = "done"
        await client.set(f"syn:runs:{run_id}", json.dumps(state_copy), ex=60 * 60 * 24 * 30)

        # History
        entry = {
            "run_id": run_id,
            "started_at": state.get("started_at", ""),
            "status": "done",
            "report_title": state.get("report_title", ""),
            "notion_url": notion_url,
        }
        raw = await client.get(_HISTORY_KEY)
        history: list = json.loads(raw) if raw else []
        history.append(entry)
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]
        await client.set(_HISTORY_KEY, json.dumps(history))

        # Clear active
        await client.delete(_ACTIVE_KEY)
        logger.info(f"[Publisher] state saved to Redis: run_id={run_id}")
    except Exception as e:
        logger.error(f"[Publisher] Redis save error: {e}")
    finally:
        await client.aclose()


async def publisher_node(state: SynState) -> dict:
    t0 = time.monotonic()
    logger.info(f"[Publisher] start run_id={state['run_id']}")

    notion_url: str | None = None
    errors: list[str] = []

    try:
        notion_url = await _publish_notion(state)
    except Exception as e:
        logger.error(f"[Publisher] Notion error: {e}")
        errors.append(f"publisher:notion:{e}")

    try:
        await _send_discord(state, notion_url)
    except Exception as e:
        logger.error(f"[Publisher] Discord error: {e}")
        errors.append(f"publisher:discord:{e}")

    await _save_to_redis(state, notion_url)

    try:
        await broadcast(
            {
                "type": "run_complete",
                "run_id": state.get("run_id"),
                "title": state.get("report_title"),
                "summary": state.get("report_summary"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"[Publisher] WebSocket broadcast error: {e}")

    logger.info(f"[Publisher] done in {time.monotonic()-t0:.1f}s")
    result: dict = {"status": "done", "current_agent": "done"}
    if errors:
        result["errors"] = errors
    return result
