# SYN — Phase 0 : Fondations & Infrastructure

## Contexte du projet

Tu construis **SYN**, un agent autonome de veille R&D pharma/biotech.
Il surveille ClinicalTrials.gov, PubMed, bioRxiv, EMA/FDA et des documents
privés clients pour produire des rapports de veille compétitive.

**Phase 0 objectif** : infrastructure complète opérationnelle.
Deliverable final : `POST /ingest/trials?query=pembrolizumab` insère des
essais réels dans PostgreSQL + Qdrant, et `GET /trials/search?q=KRAS+inhibitor`
retourne des résultats sémantiques réels.

---

## Stack imposée (ne pas dévier)

- **FastAPI** + uvicorn (async, hot-reload en dev)
- **PostgreSQL 16** via SQLAlchemy 2.x async + asyncpg
- **Qdrant** (vector store) via qdrant-client async
- **Redis 7** (state agents — Phase 2, mais infra dès maintenant)
- **Pydantic v2** + pydantic-settings pour config et validation
- **sentence-transformers** `all-MiniLM-L6-v2` (embedding Phase 0 — sera swappé BioBERT en Phase 5)
- **httpx** async pour tous les appels HTTP
- **tenacity** pour retry avec backoff exponentiel
- **loguru** pour tous les logs (pas print, pas logging stdlib)
- **Alembic** initialisé dès maintenant même si pas encore utilisé
- Docker Compose pour PG + Qdrant + Redis (FastAPI tourne en local, pas containerisé)

---

## Architecture imposée

```
syn/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan (startup/shutdown)
│   ├── config.py            # Pydantic BaseSettings — toute config via .env
│   ├── database.py          # SQLAlchemy async engine, session, Base, create_tables()
│   ├── api/
│   │   ├── __init__.py
│   │   ├── trials.py        # GET /trials/search, GET /trials/{nct_id}
│   │   └── ingest.py        # POST /ingest/trials, POST /ingest/pubmed
│   ├── models/
│   │   ├── __init__.py
│   │   └── trial.py         # ClinicalTrial SQLAlchemy ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── trial.py         # Pydantic schemas : TrialCreate, TrialResponse, IngestReport, TrialSearchParams
│   ├── services/
│   │   ├── __init__.py
│   │   ├── trial_service.py     # upsert_trial(), search_trials_hybrid(), get_by_nct_id()
│   │   └── qdrant_service.py    # ensure_collections(), upsert_trial(), search_trials(), upsert_paper()
│   └── ingestion/
│       ├── __init__.py
│       ├── clinical_trials.py   # ClinicalTrials.gov v2 API client
│       └── pubmed.py            # NCBI Entrez client (Biopython)
├── agents/                  # Vide — réservé Phase 2 LangGraph
│   └── .gitkeep
├── migrations/              # Alembic initialisé
├── docker-compose.yml
├── Dockerfile               # Pour les futures déploiements
├── requirements.txt
├── .env.example
├── .env                     # À créer depuis .env.example
└── CLAUDE.md                # Ce fichier — conventions du projet
```

---

## Exigences de qualité senior (non négociables)

### Patterns obligatoires

**UUID5 déterministe** sur toutes les entités :
```python
import uuid
trial_uuid = uuid.uuid5(uuid.NAMESPACE_URL, nct_id)
```
Jamais de `uuid4()` pour les entités ingérées — on doit pouvoir re-ingérer sans doublons.

**Upsert PostgreSQL** avec `ON CONFLICT DO UPDATE` — jamais d'INSERT brut
sur des données qui peuvent exister.

**Async partout** — pas une seule fonction bloquante dans le hot path.
`httpx.AsyncClient`, `AsyncSession`, `AsyncQdrantClient`.

**Rate limiting sur les API externes** :
- ClinicalTrials.gov : `await asyncio.sleep(0.35)` entre les pages (3 req/s)
- NCBI Entrez : 3 req/s sans API key, 10/s avec. Toujours set `Entrez.email`.

**Retry avec backoff** via tenacity sur tous les appels HTTP externes :
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
```

**Générateurs async** pour l'ingestion — ne jamais charger 500 essais en
mémoire d'un coup :
```python
async def fetch_trials(query: str, max_results: int) -> AsyncGenerator[TrialCreate, None]:
    ...
    yield trial
```

**Pas de print()** — loguru partout :
```python
from loguru import logger
logger.info("...") / logger.warning("...") / logger.error("...")
```

### PostgreSQL — modèle `ClinicalTrial`

Champs obligatoires :
- `id` UUID PK (uuid5 sur nct_id)
- `nct_id` VARCHAR(20) UNIQUE NOT NULL INDEX
- `title` TEXT
- `status` VARCHAR(50) INDEX — valeurs ClinicalTrials : RECRUITING, COMPLETED, ACTIVE_NOT_RECRUITING, etc.
- `phase` VARCHAR(20) INDEX — PHASE1, PHASE2, PHASE3, PHASE4, N_A
- `sponsor` VARCHAR(255) INDEX
- `conditions` JSONB (liste de strings)
- `interventions` JSONB (liste de {type, name})
- `primary_outcomes` JSONB (liste de {measure, timeFrame})
- `enrollment` INTEGER nullable
- `start_date` DATE nullable
- `completion_date` DATE nullable
- `raw_data` JSONB — JSON source complet, toujours stocker
- `qdrant_id` UUID nullable — linkage vers Qdrant
- `created_at` / `updated_at` TIMESTAMP auto

### Qdrant — deux collections distinctes

`syn_trials` — essais cliniques vectorisés
`syn_papers` — publications PubMed vectorisés

Ne jamais mélanger les types dans une collection.

Texte à vectoriser pour un essai :
```python
text = " | ".join([title, *conditions, *[i["name"] for i in interventions], sponsor])
```

Payload Qdrant doit toujours contenir `nct_id` pour le linkage retour vers PG.

### Recherche hybride dans `trial_service.py`

```
1. Semantic search Qdrant → top-N nct_ids avec scores
2. SELECT * FROM clinical_trials WHERE nct_id IN (...)  → données complètes PG
3. Merge : score sémantique + données PG enrichies
4. Retourner trié par score décroissant
```

### Config — `config.py`

Tout passe par `pydantic-settings` et `.env`. Zéro hardcode.
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_trials_collection: str = "syn_trials"
    qdrant_papers_collection: str = "syn_papers"
    redis_url: str = "redis://localhost:6379"
    ncbi_email: str
    ncbi_api_key: str = ""
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    environment: str = "development"
    ...
```

### Docker Compose

Services : `postgres:16-alpine`, `qdrant/qdrant:latest`, `redis:7-alpine`.
Healthchecks obligatoires sur postgres (`pg_isready`).
Volumes nommés pour persistance.
FastAPI **ne tourne pas** dans Docker Compose — en local direct via uvicorn.

### Lifespan FastAPI

```python
@asynccontextmanager
async def lifespan(app):
    await create_tables()      # crée les tables PG
    await ensure_collections() # crée les collections Qdrant
    yield
    # cleanup si besoin
```

### Endpoints

`POST /ingest/trials?query=...&max_results=100`
→ Lance fetch async ClinicalTrials, upsert PG + Qdrant, retourne `IngestReport`
```json
{"query": "pembrolizumab", "total_fetched": 87, "inserted": 82, "updated": 5, "skipped": 0, "errors": 0, "duration_seconds": 12.4}
```

`POST /ingest/pubmed?query=...&max_results=50`
→ Lance fetch NCBI Entrez, parse abstracts, vectorise, upsert Qdrant `syn_papers`

`GET /trials/search?q=...&phase=PHASE3&status=RECRUITING&limit=20`
→ Recherche hybride, retourne `{"query": "...", "count": N, "results": [...]}`

`GET /trials/{nct_id}`
→ Détail complet depuis PG

`GET /health`
→ `{"status": "ok", "service": "syn"}`

---

## ClinicalTrials.gov v2 API

URL : `https://clinicaltrials.gov/api/v2/studies`
Format : JSON
Auth : aucune
Pagination : `pageToken` dans la réponse → passer en paramètre de la requête suivante

Params clés :
- `query.term` — terme de recherche
- `pageSize` — max 1000, utiliser 50
- `format=json`

Structure réponse :
```json
{
  "studies": [...],
  "nextPageToken": "..."
}
```

Structure d'un study (champs importants) :
```
protocolSection.identificationModule.nctId
protocolSection.identificationModule.briefTitle
protocolSection.statusModule.overallStatus
protocolSection.statusModule.startDateStruct.date
protocolSection.statusModule.primaryCompletionDateStruct.date
protocolSection.designModule.phases[]
protocolSection.designModule.enrollmentInfo.count
protocolSection.sponsorCollaboratorsModule.leadSponsor.name
protocolSection.conditionsModule.conditions[]
protocolSection.armsInterventionsModule.interventions[].type/name
protocolSection.outcomesModule.primaryOutcomes[].measure/timeFrame
```

---

## NCBI Entrez (PubMed)

Utiliser **Biopython** `Bio.Entrez` :
```python
from Bio import Entrez
Entrez.email = settings.ncbi_email

# esearch → liste PMIDs
handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)

# efetch batch → abstracts XML
handle = Entrez.efetch(db="pubmed", id=",".join(pmids), rettype="xml", retmode="xml")
records = Entrez.read(handle)
```

Champs à extraire : PMID, ArticleTitle, Abstract, Journal, Year, MeSH terms.
Stocker dans Qdrant `syn_papers` avec payload `{pmid, title, journal, year, mesh_terms}`.

---

## requirements.txt complet

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic==2.10.3
pydantic-settings==2.6.1
qdrant-client==1.12.1
sentence-transformers==3.3.1
httpx==0.28.1
biopython==1.84
python-dateutil==2.9.0
redis==5.2.1
python-dotenv==1.0.1
tenacity==9.0.0
loguru==0.7.3
```

---

## Ce que tu dois produire

1. **Tous les fichiers** de l'arborescence ci-dessus, complets et fonctionnels
2. **`docker-compose.yml`** avec les 3 services + healthchecks + volumes
3. **`.env.example`** avec toutes les variables documentées
4. **`COMMANDS.md`** avec les commandes PowerShell dans l'ordre :
   - `docker compose up -d`
   - setup venv + pip install
   - `uvicorn app.main:app --reload`
   - les 4 commandes `Invoke-RestMethod` de test end-to-end
   - commandes de vérification PostgreSQL via `docker exec`

## Validation finale

Le projet est correct quand ces 3 commandes PowerShell fonctionnent sans erreur :

```powershell
# 1. Ingestion réelle
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=50" -Method POST

# 2. Recherche sémantique avec résultats
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor+lung+cancer&phase=PHASE3"

# 3. Count PostgreSQL > 0
docker exec syn-postgres psql -U syn -d syn -c "SELECT COUNT(*) FROM clinical_trials;"
```
