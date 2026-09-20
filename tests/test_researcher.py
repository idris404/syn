import asyncio
import httpx

from agents import researcher


def test_light_ingest_encodes_query_and_uses_internal_url(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"errors": 0}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, params):
            calls.append((url, params))
            return Response()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(researcher.settings, "internal_api_url", "http://fastapi:8000")
    assert asyncio.run(
        researcher._light_ingest("clinicaltrials", "lung cancer & immunotherapy")
    )
    assert calls == [
        (
            "http://fastapi:8000/ingest/trials",
            {"query": "lung cancer & immunotherapy", "max_results": 20},
        )
    ]
