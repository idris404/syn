# SYN — Phase 1 : Pipeline multi-source & RAG avancé

## État actuel du projet (Phase 0 complète)

Le projet SYN tourne sur `F:\Work\syn\`. Lis tout le code existant avant de
toucher quoi que ce soit. La Phase 0 est complète et opérationnelle :

- FastAPI sur port 8000, hot-reload
- PostgreSQL sur port **5433** (pas 5432 — déjà occupé sur la machine)
- Qdrant sur 6333, Redis sur 6379
- `POST /ingest/trials` + `GET /trials/search` fonctionnels
- **Biopython absent** (pas de wheel Python 3.13/Windows) — PubMed utilise
  NCBI E-utilities via httpx + xml.etree. Ne pas changer ça.
- Embedding : `all-MiniLM-L6-v2` (dim=384)
- Collections Qdrant : `syn_trials`, `syn_papers`

---

## Objectif Phase 1

Ajouter 3 nouvelles sources de données + améliorer le RAG existant.
**Ne rien casser** de ce qui marche en Phase 0.

### Deliverables obligatoires

1. `POST /ingest/biorxiv?query=...&max_results=50` — préprints bioRxiv
2. `POST /ingest/pdf` — upload PDF → parse → chunk → Qdrant
3. `GET /papers/search?q=...&source=pubmed|biorxiv|pdf&limit=20` — recherche sémantique sur les papers
4. `GET /trials/{nct_id}/papers` — papers PubMed/bioRxiv associés à un essai
5. EMA scraping (statique) — approbations récentes dans `syn_ema` collection Qdrant
6. RAG Q&A endpoint : `POST /rag/query` — question → retrieval Qdrant → réponse LLM Groq

---

## Ce que tu dois ajouter / modifier

### 1. Nouveaux fichiers à créer

```
app/
├── ingestion/
│   ├── biorxiv.py       # bioRxiv API client
│   ├── ema.py           # EMA EPAR scraper
│   └── pdf_parser.py    # PDF → chunks → Qdrant
├── api/
│   ├── papers.py        # GET /papers/search, GET /papers/{pmid}
│   └── rag.py           # POST /rag/query
├── models/
│   └── paper.py         # PaperRecord SQLAlchemy model (métadonnées papers)
└── services/
    └── rag_service.py   # retrieve() + generate() avec Groq
```

### 2. Fichiers à modifier

- `app/main.py` — inclure les nouveaux routers (papers, rag)
- `app/services/qdrant_service.py` — ajouter `upsert_paper()`, `search_papers()`, `ensure_collections()` étendu
- `app/schemas/trial.py` — ajouter schemas Paper, RAGQuery, RAGResponse
- `docker-compose.yml` — rien à changer
- `requirements.txt` — ajouter : `PyMuPDF`, `pdfplumber`, `python-multipart`, `groq`, `playwright`

---

## Spécifications techniques détaillées

### bioRxiv (`app/ingestion/biorxiv.py`)

API officielle : `https://api.biorxiv.org/details/biorxiv/{interval}/{cursor}/{format}`

- `interval` : ex `2024-01-01/2024-12-31` ou `30d` pour les 30 derniers jours
- `format` : `json`
- Pagination via `cursor` (offset)
- Rate limit : 1 req/s — `asyncio.sleep(1.0)` entre les pages

Champs à extraire :

```
doi, title, authors (list[str]), abstract, category, date, version
server (biorxiv|medrxiv)
```

Générateur async comme `fetch_trials()`. UUID5 sur `doi`.

Stockage : **Qdrant uniquement** dans `syn_papers`.
Payload : `{source: "biorxiv", doi, title, abstract[:500], category, date, authors}`
Texte vectorisé : `title + " " + abstract`

Endpoint :

```
POST /ingest/biorxiv?query=oncology&days=30&max_results=100
```

`days` = filtrer les N derniers jours. Default 30.

### EMA scraper (`app/ingestion/ema.py`)

URL : `https://www.ema.europa.eu/en/medicines/download-medicine-data`
CSV téléchargeable — pas de scraping dynamique nécessaire.
URL directe CSV : `https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx`

Télécharger le fichier Excel (ou CSV selon disponibilité) via httpx.
Parser avec `pandas` ou directement avec `openpyxl`.
Colonnes importantes : `Medicine name`, `Active substance`, `Product number`,
`Patient safety`, `Authorisation status`, `ATC code`, `International non-proprietary name (INN)`,
`First published`, `Revision date`, `Category`, `Generic`, `Biosimilar`,
`Orphan medicine`, `Exceptional circumstances`, `URL`

UUID5 sur `Product number`.

Nouvelle collection Qdrant : `syn_ema`.
Texte vectorisé : `medicine_name + " " + active_substance + " " + inn`
Payload : tout les champs ci-dessus.

Endpoint :

```
POST /ingest/ema
```

Pas de paramètres — télécharge et ingère tout le fichier (filtrer sur
`Authorisation status == "Authorised"`).

### PDF Parser (`app/ingestion/pdf_parser.py`)

Utiliser **PyMuPDF** (`fitz`) comme parseur principal, **pdfplumber** en fallback
pour les PDFs avec tableaux complexes.

Pipeline :

```python
1. Ouvrir le PDF avec fitz
2. Extraire le texte page par page
3. Nettoyer (strip headers/footers répétitifs, normaliser whitespace)
4. Chunking sémantique :
   - Chunk size : 512 tokens (~400 mots)
   - Overlap : 50 tokens
   - Respecter les limites de paragraphes (ne pas couper mid-phrase)
   - Détecter les sections (Abstract, Methods, Results, Discussion) et les
     stocker dans le metadata du chunk
5. UUID5 sur (filename + chunk_index)
6. Upsert Qdrant syn_papers
```

Payload par chunk :

```python
{
    "source": "pdf",
    "filename": str,
    "page": int,
    "chunk_index": int,
    "section": str,   # "abstract" | "methods" | "results" | "discussion" | "other"
    "total_chunks": int,
    "upload_id": str  # UUID4 de session d'upload
}
```

Endpoint upload :

```
POST /ingest/pdf
Content-Type: multipart/form-data
Body: file (PDF), title (str, optionnel), source_type (str: "trial_result"|"paper"|"report")
```

Utiliser `python-multipart` pour le form data FastAPI.
Taille max : 50MB. Retourner :

```json
{
  "filename": "study_results.pdf",
  "pages": 42,
  "chunks_created": 187,
  "upload_id": "uuid4",
  "duration_seconds": 3.2
}
```

### PostgreSQL — nouveau model `PaperRecord` (`app/models/paper.py`)

```python
class PaperRecord(Base):
    __tablename__ = "paper_records"
    id: UUID PK (uuid5)
    source: str  # "pubmed" | "biorxiv" | "pdf" | "ema"
    external_id: str UNIQUE  # pmid, doi, product_number, ou upload_id
    title: str
    abstract: Optional[str]
    authors: JSONB list[str]
    published_date: Optional[date]
    url: Optional[str]
    qdrant_id: Optional[UUID]
    nct_ids_mentioned: JSONB list[str]  # linkage vers essais
    metadata: JSONB  # champs spécifiques à la source
    created_at: datetime
```

Migration Alembic à générer et appliquer après création du modèle.

### RAG Service (`app/services/rag_service.py`)

```python
async def retrieve(query: str, sources: list[str] = None, limit: int = 5) -> list[dict]:
    """
    Recherche sémantique multi-collection.
    sources = ["trials", "papers", "ema"] ou None pour tout
    Merge et re-rank par score.
    """

async def generate(query: str, context: list[dict], model: str = "llama-3.3-70b-versatile") -> str:
    """
    Génère une réponse via Groq.
    context = chunks récupérés par retrieve()
    Prompt structuré : system (rôle analyste) + context + question
    """
```

Prompt système pour `generate()` :

```
Tu es un analyste senior en veille R&D pharma/biotech.
Tu réponds uniquement en te basant sur les données fournies dans le contexte.
Si l'information n'est pas dans le contexte, dis-le clairement.
Format de réponse : 2-3 paragraphes structurés, langage professionnel.
```

Endpoint RAG :

```
POST /rag/query
{
  "question": "Quels sont les essais de phase 3 en cours sur les inhibiteurs PD-1 pour le NSCLC ?",
  "sources": ["trials", "papers"],  // optionnel, défaut = tout
  "limit": 5  // nb de chunks à retriever
}
```

Réponse :

```json
{
  "question": "...",
  "answer": "...",
  "sources_used": [
    {"nct_id": "NCT...", "title": "...", "score": 0.89},
    ...
  ],
  "model": "llama-3.3-70b-versatile",
  "tokens_used": 1243
}
```

### Endpoint `/trials/{nct_id}/papers`

Dans `app/api/trials.py`, ajouter :

```
GET /trials/{nct_id}/papers
```

Logique :

1. Chercher dans Qdrant `syn_papers` les documents dont le payload
   `nct_ids_mentioned` contient `nct_id`
2. OU chercher sémantiquement avec le titre de l'essai comme query
3. Merger, dédupliquer, retourner top-10

### Endpoint `/papers/search`

```
GET /papers/search?q=...&source=pubmed&limit=20
```

Source filter via payload Qdrant `source == "pubmed"`.
Retourner : score, title, source, external_id, abstract[:300], date.

---

## Chunking — implémentation précise

```python
def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """
    Chunking en mots (plus simple et fiable que tokens pour du texte biomédical).
    chunk_size = 400 mots, overlap = 50 mots.
    Essaie de couper sur les fins de phrases (". ") quand possible.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        # Couper sur une fin de phrase si possible dans les 50 derniers mots
        if end < len(words):
            last_period = chunk.rfind(". ", len(chunk) - 300)
            if last_period > 0:
                chunk = chunk[:last_period + 1]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks
```

Détection de section (heuristique simple sur les headers) :

```python
SECTION_PATTERNS = {
    "abstract": r"(?i)^(abstract|summary|résumé)",
    "methods": r"(?i)^(methods?|materials?\s+and\s+methods?|methodology|patients?\s+and\s+methods?)",
    "results": r"(?i)^(results?|findings?|outcomes?)",
    "discussion": r"(?i)^(discussion|conclusions?|conclusion\s+and\s+discussion)",
}
```

---

## requirements.txt — ajouts Phase 1

Ajouter à la fin du requirements.txt existant :

```
# Phase 1 additions
PyMuPDF==1.24.14
pdfplumber==0.11.4
python-multipart==0.0.20
groq==0.13.1
openpyxl==3.1.5
pandas==2.2.3
```

Ne pas toucher aux versions existantes.

---

## Règles de qualité (identiques Phase 0, rappel)

- UUID5 sur tous les external IDs (doi, pmid, product_number)
- Async partout — pas de blocking calls
- Rate limiting sur toutes les APIs externes
- Retry tenacity sur les appels HTTP
- Générateurs async pour l'ingestion (pas de listes en mémoire)
- loguru pour tous les logs
- Zéro hardcode — tout passe par config.py / .env

**Ne pas régénérer** les fichiers Phase 0 qui fonctionnent. Modifier
uniquement ce qui est nécessaire (`main.py` pour les nouveaux routers,
`qdrant_service.py` pour les nouvelles collections, `requirements.txt`).

---

## Ordre d'exécution

Fais les choses dans cet ordre pour éviter les dépendances cassées :

1. `requirements.txt` — ajouter les nouvelles dépendances
2. `app/models/paper.py` — créer le model SQLAlchemy
3. `app/schemas/trial.py` — ajouter les nouveaux schemas
4. `app/services/qdrant_service.py` — étendre avec les nouvelles collections
5. `app/ingestion/biorxiv.py` — client bioRxiv
6. `app/ingestion/ema.py` — EMA scraper
7. `app/ingestion/pdf_parser.py` — PDF pipeline
8. `app/services/rag_service.py` — retrieve + generate
9. `app/api/papers.py` — endpoints papers
10. `app/api/rag.py` — endpoint RAG
11. `app/api/trials.py` — ajouter `/trials/{nct_id}/papers`
12. `app/api/ingest.py` — ajouter routes biorxiv, ema, pdf
13. `app/main.py` — inclure les nouveaux routers
14. Générer la migration Alembic pour `paper_records`

---

## Validation Phase 1

La phase est complète quand ces commandes fonctionnent sans erreur :

```powershell
# 1. Ingestion bioRxiv
Invoke-RestMethod -Uri "http://localhost:8000/ingest/biorxiv?query=KRAS+inhibitor&days=90&max_results=30" -Method POST

# 2. Ingestion EMA
Invoke-RestMethod -Uri "http://localhost:8000/ingest/ema" -Method POST

# 3. Search papers
Invoke-RestMethod -Uri "http://localhost:8000/papers/search?q=checkpoint+inhibitor+NSCLC&limit=10"

# 4. RAG query
$body = '{"question": "Quels essais de phase 3 recrutent sur les inhibiteurs PD-1 ?", "sources": ["trials"]}'
Invoke-RestMethod -Uri "http://localhost:8000/rag/query" -Method POST -Body $body -ContentType "application/json"

# 5. PDF upload (crée un PDF de test d'abord)
# Invoke-RestMethod -Uri "http://localhost:8000/ingest/pdf" -Method POST -Form @{file=Get-Item "test.pdf"}

# 6. PostgreSQL — vérifier paper_records
docker exec syn-postgres psql -U syn -d syn -c "SELECT source, COUNT(*) FROM paper_records GROUP BY source;"
```
