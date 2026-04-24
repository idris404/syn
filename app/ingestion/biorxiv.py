import asyncio
import uuid
from datetime import date, timedelta
from typing import AsyncGenerator

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api.biorxiv.org/details/biorxiv"
PAGE_SIZE = 100


def _uuid5_doi(doi: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"doi:{doi}"))


def _date_interval(days: int) -> str:
    end = date.today()
    start = end - timedelta(days=days)
    return f"{start.isoformat()}/{end.isoformat()}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _fetch_page(client: httpx.AsyncClient, interval: str, cursor: int) -> dict:
    url = f"{BASE_URL}/{interval}/{cursor}/json"
    response = await client.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def _parse_article(raw: dict) -> dict | None:
    doi = raw.get("doi", "").strip()
    if not doi:
        return None
    authors_raw = raw.get("authors", "")
    authors = [a.strip() for a in authors_raw.split(";") if a.strip()] if authors_raw else []
    return {
        "id": _uuid5_doi(doi),
        "doi": doi,
        "title": raw.get("title", "").strip(),
        "abstract": raw.get("abstract", "").strip(),
        "authors": authors,
        "category": raw.get("category", ""),
        "date": raw.get("date", ""),
        "version": raw.get("version", "1"),
        "server": raw.get("server", "biorxiv"),
    }


async def fetch_papers(
    query: str,
    days: int = 30,
    max_results: int = 100,
) -> AsyncGenerator[dict, None]:
    interval = _date_interval(days)
    fetched = 0
    cursor = 0

    async with httpx.AsyncClient() as client:
        while fetched < max_results:
            try:
                data = await _fetch_page(client, interval, cursor)
            except Exception as e:
                logger.error(f"bioRxiv fetch error at cursor={cursor}: {e}")
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for raw in collection:
                if fetched >= max_results:
                    break
                article = _parse_article(raw)
                if article is None:
                    continue
                # filter by query keyword
                text = f"{article['title']} {article['abstract']} {article['category']}".lower()
                if query.lower() not in text:
                    continue
                fetched += 1
                yield article

            total = data.get("messages", [{}])[0].get("total", 0)
            cursor += PAGE_SIZE
            if cursor >= total or cursor >= max_results * 3:
                break

            await asyncio.sleep(1.0)

    logger.info(f"bioRxiv fetch done: query={query!r} days={days} fetched={fetched}")
