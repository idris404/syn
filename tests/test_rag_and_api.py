import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.services import rag_service


def test_rag_without_context_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(rag_service.settings, "groq_api_key", "fake-key")
    answer, tokens = asyncio.run(rag_service.generate("question", []))
    assert "Aucune source" in answer
    assert tokens is None


def test_rag_api_returns_traceable_source(monkeypatch):
    async def retrieve(**kwargs):
        return [
            {
                "nct_id": "NCT12345678",
                "title": "Study",
                "score": 0.9,
                "_source_name": "trials",
            }
        ]

    async def generate(**kwargs):
        return "Answer", 10

    monkeypatch.setattr(rag_service, "retrieve", retrieve)
    monkeypatch.setattr(rag_service, "generate", generate)
    client = TestClient(app, follow_redirects=False)
    response = client.post("/rag/query", json={"question": "What happened?"})
    assert response.status_code == 200
    assert (
        response.json()["sources_used"][0]["url"]
        == "https://clinicaltrials.gov/study/NCT12345678"
    )


def test_health_without_external_services():
    # Avoid lifespan startup, which requires PostgreSQL and Qdrant.
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "service": "syn"}


def test_vision_route_reports_correct_required_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    client = TestClient(app)
    response = client.post(
        "/ingest/pdf/vision",
        files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 422
    assert "GROQ_API_KEY or OPENAI_API_KEY" in response.json()["detail"]


def test_invalid_pdf_rejected_before_parsing():
    client = TestClient(app)
    response = client.post(
        "/ingest/pdf",
        files={"file": ("sample.pdf", b"plain text", "application/pdf")},
    )
    assert response.status_code == 400


def test_rag_returns_503_when_vector_store_is_unavailable(monkeypatch):
    class Model:
        def encode(self, text):
            return self

        def tolist(self):
            return [0.1]

    async def unavailable(**kwargs):
        raise OSError("connection failed")

    monkeypatch.setattr(rag_service, "get_embedding_model", lambda: Model())
    monkeypatch.setattr(rag_service.qdrant_service, "search_papers", unavailable)
    client = TestClient(app)
    response = client.post("/rag/query", json={"question": "What happened?"})
    assert response.status_code == 503


def test_pdf_search_exposes_a_chunk_identifier(monkeypatch):
    from app.api import papers

    class Model:
        def encode(self, text):
            return self

        def tolist(self):
            return [0.1]

    async def search_papers(**kwargs):
        return [
            {
                "source": "pdf",
                "upload_id": "demo-upload",
                "chunk_index": 2,
                "title": "Synthetic PDF",
                "score": 0.7,
            }
        ]

    monkeypatch.setattr(papers, "get_embedding_model", lambda: Model())
    monkeypatch.setattr(papers.qdrant_service, "search_papers", search_papers)
    response = TestClient(app).get("/papers/search?q=synthetic")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "pdf:demo-upload:2"


def test_websocket_connection_is_removed_on_disconnect():
    from app.api.ws import _connections

    client = TestClient(app)
    with client.websocket_connect("/ws/alerts"):
        assert len(_connections) == 1
    assert _connections == []


def test_ema_ingestion_respects_small_limit(monkeypatch):
    from app.api import ingest

    class Model:
        def encode(self, text):
            return self

        def tolist(self):
            return [0.1]

    async def medicines():
        for index in range(3):
            yield {
                "id": f"medicine-{index}",
                "product_number": f"EMA-{index}",
                "medicine_name": "Demo",
                "active_substance": "demo",
                "inn": "demo",
                "atc_code": "",
                "authorisation_status": "Authorised",
                "category": "Human",
                "orphan_medicine": "No",
                "first_published": "",
                "revision_date": "",
                "url": "",
            }

    written = []

    async def upsert_paper(**kwargs):
        written.append(kwargs)

    monkeypatch.setattr(ingest.ema, "fetch_medicines", medicines)
    monkeypatch.setattr(ingest.trial_service, "get_embedding_model", lambda: Model())
    monkeypatch.setattr(ingest.qdrant_service, "upsert_paper", upsert_paper)
    response = TestClient(app).post("/ingest/ema?max_results=1")
    assert response.status_code == 200
    assert response.json()["total_fetched"] == 1
    assert len(written) == 1
