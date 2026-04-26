# SYN - Clinical Trial & Pipeline Intelligence

> Agent autonome de veille R&D pharma/biotech. Il surveille les essais cliniques,
> les publications scientifiques et les approbations reglementaires en continu,
> puis produit des rapports de veille competitive rediges comme un analyste senior.

## Ce que SYN fait

- Ingestion multi-source: ClinicalTrials.gov, PubMed, bioRxiv, EMA
- Vision AI: extraction et interpretation de courbes Kaplan-Meier, forest plots et tableaux depuis des PDF scientifiques
- Agents autonomes: pipeline LangGraph (Planner -> Researcher -> Analyzer -> Writer -> Publisher)
- RAG sur documents prives: indexation de documents confidentiels client (brevets, pipeline R&D) et croisement avec donnees publiques
- Dashboard temps reel: Next.js 15 avec alertes WebSocket

## Architecture

```text
Sources (ClinicalTrials / PubMed / bioRxiv / EMA / PDFs)
  -> ingestion async + rate limiting + UUID5 deterministe
PostgreSQL (metadonnees) + Qdrant (4 collections vectorielles)
  -> LangGraph multi-agents (Planner -> Researcher -> Analyzer -> Writer -> Publisher)
Notion (rapports) + Discord (alertes) + Dashboard Next.js 15
```

## Stack technique

| Couche | Technologie |
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

## Lancer le projet (dev)

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

## Lancer le projet (production locale)

```bash
cp .env.prod.example .env.prod
# Renseigner les variables dans .env.prod

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

## Validation Phase 5

```powershell
# 1. Build Docker local
docker compose --env-file .env.prod -f docker-compose.prod.yml build

# 2. Lancer la stack prod en local
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 3. Verifier FastAPI containerise
Invoke-RestMethod -Uri "http://localhost:8000/health"
Invoke-RestMethod -Uri "http://localhost:8000/kpis"

# 4. Verifier le dashboard
Start-Process "http://localhost:3000"

# 5. Test ingestion end-to-end
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=20" -Method POST
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor"

# 6. Arret propre
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

## Deploiement Railway

1. Creer un compte Railway: https://railway.app
2. New Project -> Deploy from GitHub repo -> selectionner le repo SYN
3. Railway detecte automatiquement le `Dockerfile`
4. Ajouter les variables d'environnement depuis `.env.prod.example`
5. Ajouter les services PostgreSQL et Redis via plugins Railway
6. Deployer Qdrant avec l'image `qdrant/qdrant`
7. Mettre a jour `ALLOWED_ORIGINS` avec l'URL publique Railway

## Cas d'usage - Veille competitive biotech

SYN est concu pour des equipes R&D pharma/biotech qui ont besoin de:

- Surveiller les essais concurrents en temps reel
- Croiser les donnees publiques avec leurs documents R&D internes confidentiels
- Recevoir des rapports de veille structures sans intervention manuelle

Contact demonstration / mission freelance: [votre email] | [LinkedIn]
