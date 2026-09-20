# SYN — experimental pharmaceutical evidence monitor

SYN is a personal Applied AI project for exploring clinical trials, publications and European medicine records in one local workspace. It ingests selected public sources, indexes text in Qdrant, and exposes search and a small agent workflow through FastAPI and a Next.js interface. It is a prototype, not a validated medical or commercial intelligence product.

## What works today

- On-demand ingestion from ClinicalTrials.gov, PubMed, bioRxiv and an EMA spreadsheet. Clinical trials are stored in PostgreSQL and Qdrant; publications and EMA records currently go to Qdrant only. There is no FDA integration.
- Semantic search uses `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions). RAG retrieval returns indexed source metadata; answer generation needs `GROQ_API_KEY`. Without indexed context it declines to answer, and without a Groq key it reports that generation is unavailable.
- PDF text is chunked and indexed in Qdrant. A separate experimental figure workflow renders candidate pages and uses Groq or OpenAI vision when configured; extracted values are model interpretations, not verified measurements.
- The LangGraph planner → researcher → analyzer → writer → publisher workflow can be triggered manually. Without Groq it uses fixed targets and produces a limited fallback report. Notion and Discord output require their own credentials. Scheduler runs are **disabled by default**.
- The dashboard supports search, ingestion, reports and a WebSocket alert connection in the local setup. WebSocket connections are process-local and are not durable notifications.

There is no authentication, tenant identity, data isolation, rate limiting or confidential-document access policy. **Run SYN locally with public or synthetic data only. Do not expose this stack to the internet or upload private documents.** The included Compose deployment and Railway files are experiments, not evidence of a secured deployment.

## Architecture

```text
ClinicalTrials.gov ──→ PostgreSQL + Qdrant (syn_trials)
PubMed / bioRxiv ────→ Qdrant (syn_papers)
EMA spreadsheet ────→ Qdrant (syn_ema)
PDF text / figures ─→ Qdrant (syn_papers / syn_figures)
                       PostgreSQL (figure_records)
Qdrant ─→ retrieval / optional Groq answer ─→ FastAPI ─→ Next.js
                     LangGraph agents ─→ Redis run state
                                      └→ optional Notion / Discord
```

Source-specific IDs are used for trial and publication vector upserts. The repository contains no reproducible evidence for a populated dataset size. The active embedding model is MiniLM.

## Local setup

Prerequisites: Python 3.12, Node.js 20+, npm, and a running Docker daemon with Compose. The first backend installation downloads PyTorch and the first search downloads the embedding model. External ingestion needs internet access. PubMed requests need a real contact email in `NCBI_EMAIL`; an NCBI API key is optional.

```bash
cp .env.example .env
# Set NCBI_EMAIL to your own email in .env
docker compose up -d
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [the UI](http://localhost:3000) or [the API documentation](http://localhost:8000/docs). The API creates PostgreSQL tables and Qdrant collections at startup. `GET /health` checks the API process only. If PostgreSQL or Qdrant is unavailable, startup fails. Redis is needed for agent runs and KPIs.

## Five-minute local demo

With the services and both apps running, ingest a small public sample, then search it:

```bash
curl -fsS -X POST 'http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=5'
curl -fsS 'http://localhost:8000/trials/search?q=pembrolizumab'
curl -fsS 'http://localhost:8000/kpis'
```

The ingestion response reports fetched, inserted, updated and error counts. Check `errors` before interpreting search results. Results depend on live ClinicalTrials.gov availability and the model download. The RAG endpoint (`POST /rag/query`) retrieves from Qdrant; set `GROQ_API_KEY` only if you want generated answers. Treat every generated answer and figure extraction as unverified until checked against its original source.

## Automated checks

The backend checks use mocks and do not need Docker, API keys or a model download:

```bash
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m ruff check app agents tests --select E4,E7,E9,F
.venv/bin/python -m ruff format --check tests
.venv/bin/python -m compileall -q app agents tests
.venv/bin/python -m pytest -q
cd frontend
npm ci
npm audit --audit-level=high
npm run lint
npm run typecheck
npm run build
```

GitHub Actions runs these same checks without secrets. The CI is present in the repository; a successful public run has not been verified here.

## Known limits

- Trial PostgreSQL and Qdrant writes are separate, so a Qdrant failure can leave an indexed trial missing until retry. Publication and EMA ingestion is vector-only; the PostgreSQL `paper_records` table and its KPI are not populated by those routes.
- The search ranking is vector similarity, not evidence quality. RAG returns source identifiers where available, but generated prose has no enforced claim-by-claim citation check. PDF uploads are not isolated by user.
- bioRxiv search applies a simple keyword filter to fetched recent records. Figure detection is heuristic and vision output may be wrong. WebSocket alerts work only inside one backend process.
- Agent publishing and external integrations are implemented but have not been verified against live accounts in this repository. The local tests cover selected logic and API responses, not a full end-to-end stack.
- The API has no authentication, authorization, tenant separation, upload quota, or request rate limit. Public deployment and confidential data are out of scope until these are addressed and tested.

This README supersedes the earlier phase-plan notes in `CLAUDE.md` and `COMMANDS.md` where they describe the system as deployed or complete.
