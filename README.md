# SYN - Clinical Trial & Pipeline Intelligence

> Autonomous pharma/biotech R&D intelligence agent. It continuously monitors clinical trials,
> scientific publications, and regulatory approvals,
> then produces competitive intelligence reports written like a senior analyst.

## What SYN Does

- Multi-source ingestion: ClinicalTrials.gov, PubMed, bioRxiv, EMA
- Vision AI: extraction and interpretation of Kaplan-Meier curves, forest plots, and tables from scientific PDFs
- Autonomous agents: LangGraph pipeline (Planner -> Researcher -> Analyzer -> Writer -> Publisher)
- RAG on private documents: indexing confidential client documents (patents, R&D pipeline) and cross-referencing with public data
- Real-time dashboard: Next.js 15 with WebSocket alerts

## Architecture

```text
Sources (ClinicalTrials / PubMed / bioRxiv / EMA / PDFs)
  -> async ingestion + rate limiting + deterministic UUID5
PostgreSQL (metadata) + Qdrant (4 vector collections)
  -> LangGraph multi-agents (Planner -> Researcher -> Analyzer -> Writer -> Publisher)
Notion (reports) + Discord (alerts) + Next.js 15 dashboard
```

## Technical Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy async + asyncpg |
| Vector DB | Qdrant - syn_trials, syn_papers, syn_ema, syn_figures |
| Relational DB | PostgreSQL 16 |
| Cache / State agents | Redis 7 |
| Agents | LangGraph + Groq llama-3.3-70b |
| Vision AI | Groq llama-3.2-90b-vision |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (dim=384) |
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui |
| Infra | Docker Compose + Railway |

## Screenshots (placeholders)

- Dashboard overview: `docs/screenshots/dashboard-overview.png`
- Search trials: `docs/screenshots/trials-search.png`
- Generated report: `docs/screenshots/report-detail.png`

## Run the Project (dev)

```bash
# 1) Services (PostgreSQL + Qdrant + Redis)
docker compose up -d

# 2) Backend
python -m venv .venv
# PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload

# 3) Frontend
cd frontend
npm install
npm run dev
```

Swagger UI: http://localhost:8000/docs
Dashboard: http://localhost:3000

## Run the Project (local production)

```bash
cp .env.prod.example .env.prod
# Fill in variables inside .env.prod

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

## Phase 5 Validation

```powershell
# 1. Local Docker build
docker compose --env-file .env.prod -f docker-compose.prod.yml build

# 2. Start the local production stack
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 3. Verify containerized FastAPI
Invoke-RestMethod -Uri "http://localhost:8000/health"
Invoke-RestMethod -Uri "http://localhost:8000/kpis"

# 4. Verify the dashboard
Start-Process "http://localhost:3000"

# 5. End-to-end ingestion test
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=20" -Method POST
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor"

# 6. Clean shutdown
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

## Railway Deployment

1. Create a Railway account: https://railway.app
2. New Project -> Deploy from GitHub repo -> select the SYN repository
3. Railway automatically detects the `Dockerfile`
4. Add environment variables from `.env.prod.example`
5. Add PostgreSQL and Redis services via Railway plugins
6. Deploy Qdrant using the `qdrant/qdrant` image
7. Update `ALLOWED_ORIGINS` with the public Railway URL

## Use Case - Biotech Competitive Intelligence

SYN is designed for pharma/biotech R&D teams that need to:

- Monitor competitor trials in real time
- Cross-reference public data with confidential internal R&D documents
- Receive structured intelligence reports without manual effort

Contact for demo / freelance engagement: [your email] | [LinkedIn]
