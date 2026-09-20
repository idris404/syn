from app.ingestion.biorxiv import _parse_article
from app.ingestion import biorxiv
from app.ingestion import ema
from app.ingestion.clinical_trials import _extract_trial
from app.ingestion.pdf_parser import chunk_id, chunk_text
from app.ingestion.pubmed import _parse_xml
from agents.planner import _PLANNER_PROMPT
from app.database import Base
from app.models import figure, paper, trial


def test_trial_parser_requires_identifier():
    assert (
        _extract_trial(
            {"protocolSection": {"identificationModule": {"briefTitle": "No ID"}}}
        )
        is None
    )
    trial = _extract_trial(
        {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT12345678", "briefTitle": "Study"}
            }
        }
    )
    assert trial.nct_id == "NCT12345678"


def test_pubmed_xml_nested_abstract():
    xml = "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12</PMID><Article><ArticleTitle>A <i>study</i></ArticleTitle><Abstract><AbstractText>Result</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"
    assert _parse_xml(xml)[0]["title"] == "A study"
    assert _parse_xml(xml)[0]["abstract"] == "Result"


def test_biorxiv_dedup_id_is_stable():
    raw = {"doi": "10.1234/example", "title": " Study ", "authors": "A; B"}
    assert _parse_article(raw)["id"] == _parse_article(raw)["id"]
    assert _parse_article(raw)["authors"] == ["A", "B"]
    assert _parse_article({}) is None


def test_biorxiv_total_string_does_not_crash(monkeypatch):
    import asyncio

    async def page(client, interval, cursor):
        return {
            "collection": [{"doi": "10.1234/example", "title": "Cancer study"}],
            "messages": [{"total": "100"}],
        }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(biorxiv, "_fetch_page", page)
    monkeypatch.setattr(biorxiv.httpx, "AsyncClient", lambda: Client())

    async def collect():
        return [paper async for paper in biorxiv.fetch_papers("cancer", max_results=1)]

    assert len(asyncio.run(collect())) == 1


def test_ema_current_spreadsheet_layout(monkeypatch):
    import asyncio
    import io

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Content type:", "Medicine"])
    for _ in range(7):
        sheet.append([])
    sheet.append(
        [
            "Category",
            "Name of medicine",
            "EMA product number",
            "Medicine status",
            "Active substance",
            "Medicine URL",
        ]
    )
    sheet.append(
        [
            "Human",
            "Demo medicine",
            "EMEA/H/C/123",
            "Authorised",
            "demo substance",
            "https://www.ema.europa.eu/demo",
        ]
    )
    sheet.append(["Human", "Other medicine", "EMEA/H/C/456", "Withdrawn", "other", ""])
    buffer = io.BytesIO()
    workbook.save(buffer)

    async def download():
        return buffer.getvalue()

    monkeypatch.setattr(ema, "_download_xlsx", download)

    async def collect():
        return [medicine async for medicine in ema.fetch_medicines()]

    medicines = asyncio.run(collect())
    assert len(medicines) == 1
    assert medicines[0]["product_number"] == "EMEA/H/C/123"
    assert medicines[0]["medicine_name"] == "Demo medicine"


def test_pdf_chunks_retain_all_words_and_uploads_have_distinct_ids():
    words = [f"word{i}" for i in range(23)]
    chunks = chunk_text(" ".join(words), chunk_size=10, overlap=2)
    assert len(chunks) == 3
    assert chunks[-1].split()[-1] == "word22"
    assert chunk_id("upload-one", 0) != chunk_id("upload-two", 0)


def test_planner_prompt_formats_with_literal_json_example():
    prompt = _PLANNER_PROMPT.format(recent_runs="none", today="2026-09-20")
    assert '{"targets": [...], "reasoning": "..."}' in prompt


def test_all_persisted_models_are_registered():
    names = {
        figure.FigureRecord.__tablename__,
        paper.PaperRecord.__tablename__,
        trial.ClinicalTrial.__tablename__,
    }
    assert names.issubset(Base.metadata.tables)
