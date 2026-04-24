import asyncio
import xml.etree.ElementTree as ET
from typing import AsyncGenerator

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _base_params() -> dict:
    params = {"email": settings.ncbi_email, "tool": "syn-agent"}
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    return params


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _esearch(client: httpx.AsyncClient, query: str, max_results: int) -> list[str]:
    params = {**_base_params(), "db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    response = await client.get(ESEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("esearchresult", {}).get("idlist", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _efetch(client: httpx.AsyncClient, pmids: list[str]) -> list[dict]:
    params = {**_base_params(), "db": "pubmed", "id": ",".join(pmids), "rettype": "xml", "retmode": "xml"}
    response = await client.get(EFETCH_URL, params=params, timeout=60)
    response.raise_for_status()
    return _parse_xml(response.text)


def _text(element, path: str) -> str:
    node = element.find(path)
    return "".join(node.itertext()).strip() if node is not None else ""


def _parse_xml(xml_text: str) -> list[dict]:
    papers = []
    try:
        root = ET.fromstring(xml_text)
        for article in root.findall(".//PubmedArticle"):
            try:
                medline = article.find("MedlineCitation")
                if medline is None:
                    continue

                pmid = _text(medline, "PMID")
                art = medline.find("Article")
                if art is None:
                    continue

                title = _text(art, "ArticleTitle")
                abstract_parts = [
                    "".join(node.itertext()).strip()
                    for node in art.findall(".//AbstractText")
                ]
                abstract = " ".join(p for p in abstract_parts if p)
                journal = _text(art, "Journal/Title")

                pub_date = art.find(".//PubDate")
                year = _text(pub_date, "Year") if pub_date is not None else ""
                if not year:
                    year = _text(pub_date, "MedlineDate")[:4] if pub_date is not None else ""

                mesh_terms = [
                    "".join(desc.itertext()).strip()
                    for desc in medline.findall(".//MeshHeading/DescriptorName")
                ]

                papers.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                    "journal": journal,
                    "year": year,
                    "mesh_terms": mesh_terms,
                })
            except Exception as e:
                logger.warning(f"Failed to parse PubMed article: {e}")
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
    return papers


async def fetch_papers(query: str, max_results: int = 50) -> AsyncGenerator[dict, None]:
    async with httpx.AsyncClient() as client:
        pmids = await _esearch(client, query, max_results)
        logger.info(f"PubMed esearch '{query}' → {len(pmids)} PMIDs")

        if not pmids:
            return

        batch_size = 20
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            papers = await _efetch(client, batch)
            for paper in papers:
                yield paper
            await asyncio.sleep(0.35)
