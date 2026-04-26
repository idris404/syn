# SYN — Phase 5 : Production & Deploy

## État actuel du projet (Phases 0→4 complètes)

Lis tout le code existant avant de toucher quoi que ce soit.

**Backend FastAPI** port 8000 — tous les endpoints opérationnels
**Frontend Next.js 15** dans `frontend/` — build validé, 6 pages, WebSocket
**Embedding** : `all-MiniLM-L6-v2` (dim=384) — on ne change pas ça
**Collections Qdrant** : syn_trials, syn_papers, syn_ema, syn_figures
**PostgreSQL 5433** : ClinicalTrial, PaperRecord, FigureRecord
**Biopython absent** — PubMed via httpx + xml.etree, ne pas changer

---

## Objectif Phase 5

Rendre SYN déployable et accessible publiquement via une URL Railway.
Objectif : envoyer un lien qui marche à PredictCan ou un client biotech.

### Deliverables obligatoires

1. `Dockerfile` FastAPI production-ready
2. `frontend/Dockerfile` Next.js standalone
3. `docker-compose.prod.yml` — stack complète (FastAPI + PG + Qdrant + Redis + Frontend)
4. `.env.prod.example` — variables de production documentées
5. `railway.toml` — config déploiement Railway pour FastAPI
6. `README.md` — portfolio complet avec architecture, stack, screenshots placeholder, quick start

---

## Nouveaux fichiers à créer

```
syn/
├── Dockerfile                   # FastAPI production
├── docker-compose.prod.yml      # Stack complète prod
├── .env.prod.example            # Variables prod documentées
├── railway.toml                 # Config Railway
├── .dockerignore
├── README.md                    # Portfolio README
└── frontend/
    └── Dockerfile               # Next.js standalone
```

## Fichiers à modifier

- `frontend/next.config.ts` — ajouter `output: 'standalone'`
- `app/config.py` — ajouter `allowed_origins` configurable pour CORS prod
- `app/main.py` — CORS origins depuis config (pas hardcodé localhost)
- `.gitignore` — ajouter patterns prod

---

## Spécifications techniques

### `Dockerfile` FastAPI

```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharger le modèle embedding dans l'image
# Évite un cold start de 30s au premier démarrage
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app/ ./app/
COPY agents/ ./agents/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### `frontend/Dockerfile` — Next.js standalone

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

### `frontend/next.config.ts` — modifier

Ajouter `output: 'standalone'` à la config existante :

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // AJOUTER — nécessaire pour le Dockerfile
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: process.env.NEXT_PUBLIC_API_URL
          ? `${process.env.NEXT_PUBLIC_API_URL}/:path*`
          : "http://localhost:8000/:path*",
      },
    ];
  },
};
export default nextConfig;
```

### `docker-compose.prod.yml`

```yaml
services:
  fastapi:
    build: .
    container_name: syn-api
    ports:
      - "8000:8000"
    env_file: .env.prod
    environment:
      - DATABASE_URL=postgresql+asyncpg://syn:${POSTGRES_PASSWORD}@postgres:5432/syn
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      redis:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    container_name: syn-postgres
    environment:
      POSTGRES_USER: syn
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: syn
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U syn -d syn"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    container_name: syn-qdrant
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: syn-redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 5s
      retries: 5
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: syn-frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://fastapi:8000
    depends_on:
      - fastapi
    restart: unless-stopped

volumes:
  pg_data:
  qdrant_data:
  redis_data:
```

### `.env.prod.example`

```bash
# PostgreSQL
POSTGRES_PASSWORD=change_me_strong_password

# Redis
REDIS_PASSWORD=change_me_strong_password

# Base URLs (dans le container, on utilise les noms de service Docker)
DATABASE_URL=postgresql+asyncpg://syn:POSTGRES_PASSWORD@postgres:5432/syn
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://:REDIS_PASSWORD@redis:6379

# AI APIs
GROQ_API_KEY=gsk_...
VISION_PROVIDER=groq

# NCBI
NCBI_EMAIL=ton@email.com

# Outputs
NOTION_TOKEN=secret_...
NOTION_REPORTS_DB_ID=...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# App
ENVIRONMENT=production
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384
LOG_LEVEL=INFO

# CORS — frontend URL en production
ALLOWED_ORIGINS=https://syn.up.railway.app,http://localhost:3000
```

### `app/config.py` — modifier

Ajouter :

```python
allowed_origins: list[str] = ["http://localhost:3000"]
```

### `app/main.py` — modifier CORS

Remplacer le `allow_origins` hardcodé par :

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### `railway.toml`

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2"
restartPolicyType = "on-failure"
restartPolicyMaxRetries = 3

[environments.production]
PORT = "8000"
```

### `.dockerignore`

```
.venv/
__pycache__/
*.pyc
*.pyo
.env
.env.*
!.env.prod.example
.git/
.gitignore
frontend/
dataset/
models/
notebooks/
*.md
docker-compose*.yml
```

### `.gitignore` — ajouter

```
# Production secrets
.env.prod

# ML artifacts (Phase 5 optionnelle)
dataset/*.jsonl
models/syn-*/

# Python
__pycache__/
*.pyc
.venv/

# Node
frontend/node_modules/
frontend/.next/
```

---

## README.md — Portfolio

Rédiger un README complet dans ce style :

```markdown
# SYN — Clinical Trial & Pipeline Intelligence

> Agent autonome de veille R&D pharma/biotech. Surveille les essais cliniques,
> les publications scientifiques et les approbations réglementaires en continu,
> et produit des rapports de veille compétitive rédigés comme un analyste senior.

## Ce que SYN fait

- **Ingestion multi-source** : ClinicalTrials.gov, PubMed, bioRxiv, EMA
- **Vision AI** : extrait et interprète les courbes Kaplan-Meier, forest plots,
  et tableaux de résultats depuis des PDFs scientifiques complexes
- **Agents autonomes** : pipeline LangGraph — Planner décide seul des cibles,
  Researcher collecte, Analyzer croise public + privé, Writer rédige, Publisher livre
- **RAG sur documents privés** : indexe les documents confidentiels client
  (brevets, pipeline R&D) et les croise avec les données publiques
- **Dashboard temps réel** : Next.js 15 avec alertes WebSocket

## Architecture
```

Sources (ClinicalTrials / PubMed / bioRxiv / EMA / PDFs)
↓ ingestion async + rate limiting + UUID5 déterministe
PostgreSQL (métadonnées) + Qdrant (4 collections vectorielles)
↓ LangGraph multi-agents (Planner → Researcher → Analyzer → Writer → Publisher)
Notion (rapports) + Discord (alertes) + Dashboard Next.js 15

````

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI + SQLAlchemy async + asyncpg |
| Vector DB | Qdrant — syn_trials, syn_papers, syn_ema, syn_figures |
| Relational DB | PostgreSQL 16 |
| Cache / State agents | Redis 7 |
| Agents | LangGraph + Groq llama-3.3-70b |
| Vision AI | Groq llama-3.2-90b-vision — figures PDF |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 |
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui |
| Infra | Docker Compose |

## Lancer le projet (dev)

```bash
# 1. Services (PostgreSQL + Qdrant + Redis)
docker compose up -d

# 2. Backend
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev
````

Swagger UI : http://localhost:8000/docs
Dashboard : http://localhost:3000

## Lancer le projet (production)

```bash
cp .env.prod.example .env.prod
# Remplir les variables dans .env.prod
docker compose -f docker-compose.prod.yml up -d
```

## Cas d'usage — Veille compétitive biotech

SYN a été conçu pour des équipes R&D pharma/biotech qui ont besoin de :

- Surveiller les essais concurrents en temps réel
- Croiser les données publiques avec leurs documents R&D internes confidentiels
- Recevoir des rapports de veille structurés sans intervention manuelle

**Contactez-moi pour une démonstration ou une mission freelance** :
[votre email] | [LinkedIn]

````

---

## Ordre d'exécution

1. `.dockerignore` — créer
2. `Dockerfile` — FastAPI prod
3. `frontend/Dockerfile` — Next.js standalone
4. `frontend/next.config.ts` — ajouter `output: 'standalone'` + env API URL
5. `app/config.py` — ajouter `allowed_origins`
6. `app/main.py` — CORS depuis config
7. `.env.prod.example` — toutes les variables documentées
8. `docker-compose.prod.yml` — stack complète
9. `railway.toml` — config Railway
10. `.gitignore` — mettre à jour
11. `README.md` — rédiger le portfolio complet

---

## Validation Phase 5

```powershell
# 1. Build Docker local — test que tout compile
docker compose -f docker-compose.prod.yml build
# → Aucune erreur de build sur les 2 images (fastapi + frontend)

# 2. Lancer la stack prod en local
docker compose -f docker-compose.prod.yml up -d
# Attendre 30s le temps que les services démarrent

# 3. Vérifier FastAPI containerisé
Invoke-RestMethod -Uri "http://localhost:8000/health"
# → {"status": "ok", "service": "syn"}

Invoke-RestMethod -Uri "http://localhost:8000/kpis"
# → chiffres réels (DB vide au premier run, c'est normal)

# 4. Vérifier le dashboard
Start-Process "http://localhost:3000"
# → Dashboard SYN s'affiche dans le browser

# 5. Test ingestion end-to-end depuis la stack prod
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=20" -Method POST
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor"
# → résultats réels

# 6. Arrêt propre
docker compose -f docker-compose.prod.yml down
````

## Déploiement Railway (instructions manuelles après)

Railway ne se configure pas via Claude Code — c'est une action manuelle :

1. Créer un compte Railway : https://railway.app
2. `New Project` → `Deploy from GitHub repo` → sélectionner le repo SYN
3. Railway détecte le `Dockerfile` automatiquement
4. Ajouter les variables d'env depuis `.env.prod.example` dans le dashboard Railway
5. Ajouter les services : `PostgreSQL` (plugin Railway), `Redis` (plugin Railway)
6. Pour Qdrant : déployer depuis `qdrant/qdrant` image Docker sur Railway
7. Une fois déployé : copier l'URL publique Railway dans `ALLOWED_ORIGINS`
