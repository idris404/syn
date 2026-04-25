# SYN — Phase 2 : LangGraph Multi-Agents

## État actuel du projet (Phases 0 + 1 complètes)

Le projet SYN tourne sur `F:\Work\syn\`. Lis tout le code existant avant
de toucher quoi que ce soit.

**Phase 0 opérationnelle :**

- PostgreSQL port 5433, Qdrant 6333, Redis 6379
- `ClinicalTrial` model + upsert UUID5
- `POST /ingest/trials` + `GET /trials/search` (hybride PG + Qdrant)
- Collections Qdrant : `syn_trials`, `syn_papers`
- Embedding : `all-MiniLM-L6-v2` dim=384
- Biopython absent — PubMed via httpx + xml.etree

**Phase 1 opérationnelle :**

- `PaperRecord` model + migration Alembic appliquée
- `POST /ingest/biorxiv`, `/ingest/ema`, `/ingest/pdf`
- `GET /papers/search`, `GET /trials/{nct_id}/papers`
- `POST /rag/query` — retrieve Qdrant + generate Groq llama-3.3-70b
- Collection Qdrant : `syn_ema`
- RAG service : `retrieve()` multi-collection + `generate()`
- Chunking sémantique PDF : 400 mots / 50 overlap, détection sections
- Dépendances Phase 1 installées : PyMuPDF, pdfplumber, groq, pandas, openpyxl

---

## Objectif Phase 2

Construire le **graph LangGraph multi-agents** qui orchestre la veille
de manière autonome. Quatre agents : Planner, Researcher, Analyzer, Writer.

Le Planner décide seul quoi surveiller et quand. Un run complet produit
un rapport de veille structuré publié dans Notion + Discord.

### Deliverables obligatoires

1. Graph LangGraph complet avec les 4 agents
2. State persistant Redis — les runs survivent aux restarts
3. Scheduling autonome APScheduler — le Planner se déclenche seul
4. `POST /agents/run` — lancer un run manuel
5. `GET /agents/runs` — historique des runs
6. `GET /agents/runs/{run_id}` — détail + statut temps réel
7. Publication Notion — rapport structuré dans une database Notion
8. Alerte Discord — résumé + lien Notion via webhook

---

## Architecture des agents

### State partagé (LangGraph `TypedDict`)

```python
# agents/state.py
from typing import TypedDict, Annotated, Optional
from datetime import datetime
import operator

class SynState(TypedDict):
    # Identity
    run_id: str
    started_at: str

    # Planner output
    targets: list[dict]        # [{query, source, priority, reason}]
    plan_reasoning: str

    # Researcher output
    raw_results: Annotated[list[dict], operator.add]   # accumulation
    sources_searched: Annotated[list[str], operator.add]

    # Analyzer output
    analysis: str
    key_findings: list[dict]   # [{finding, evidence, importance: high|med|low}]
    competitor_updates: list[dict]

    # Writer output
    report_title: str
    report_body: str           # Markdown complet
    report_summary: str        # 3 phrases max pour Discord

    # Routing & control
    errors: Annotated[list[str], operator.add]
    current_agent: str
    status: str                # planning|researching|analyzing|writing|done|failed
```

### Planner (`agents/planner.py`)

**Rôle** : Décide quoi surveiller dans ce run. Consulte Redis pour savoir
ce qui a déjà été fait récemment et éviter les doublons.

```python
async def planner_node(state: SynState) -> dict:
    """
    Inputs  : rien (premier node du graph)
    Outputs : targets (liste de requêtes à exécuter), plan_reasoning

    Logique :
    1. Récupérer depuis Redis les derniers runs (clé: "syn:runs:history")
    2. Appeler Groq pour décider des cibles prioritaires
    3. Retourner max 5 targets avec source + priorité + raison
    """
```

Prompt Planner :

```
Tu es un analyste R&D pharma/biotech. Tu dois décider quoi surveiller
aujourd'hui dans le pipeline de veille compétitive.

Derniers runs : {recent_runs}
Date du jour : {today}

Génère une liste de 3 à 5 cibles de recherche prioritaires.
Pour chaque cible, spécifie :
- query : terme de recherche précis
- source : "clinicaltrials" | "pubmed" | "biorxiv" | "ema"
- priority : "high" | "medium" | "low"
- reason : pourquoi c'est pertinent maintenant (1 phrase)

Réponds UNIQUEMENT en JSON valide :
{"targets": [...], "reasoning": "..."}
```

### Researcher (`agents/researcher.py`)

**Rôle** : Exécute les recherches décidées par le Planner en parallèle.

```python
async def researcher_node(state: SynState) -> dict:
    """
    Inputs  : state.targets
    Outputs : raw_results (accumulés), sources_searched

    Pour chaque target, appelle le service d'ingestion correspondant
    ET fait une recherche Qdrant pour les données déjà indexées.
    Parallélisme via asyncio.gather() — toutes les targets en même temps.
    """
```

Important : le Researcher **n'ingère pas** de nouvelles données dans ce
node (ça prendrait trop longtemps). Il cherche dans ce qui est déjà
indexé dans Qdrant + lance une ingestion légère (max 20 résultats) en
arrière-plan si la dernière ingestion sur cette query date de plus de 24h
(vérifier Redis).

### Analyzer (`agents/analyzer.py`)

**Rôle** : Croise les résultats bruts avec les données RAG pour produire
une analyse structurée.

```python
async def analyzer_node(state: SynState) -> dict:
    """
    Inputs  : state.raw_results, state.targets
    Outputs : analysis (texte), key_findings, competitor_updates

    Logique :
    1. Pour chaque groupe de résultats, appel RAG rag_service.retrieve()
    2. Construire un contexte enrichi (résultats bruts + chunks RAG)
    3. Appel Groq pour analyser et extraire les findings clés
    4. Identifier les mises à jour concurrentes (nouveaux essais, nouvelles phases)
    """
```

Prompt Analyzer :

```
Tu es un analyste senior R&D pharma/biotech.
Analyse les données suivantes et identifie les points clés.

Données collectées : {raw_results_summary}
Contexte documentaire : {rag_context}

Produis :
1. Une analyse synthétique (3-4 paragraphes)
2. Les findings clés (max 5) avec niveau d'importance
3. Les mises à jour concurrentes notables

Réponds UNIQUEMENT en JSON valide :
{
  "analysis": "...",
  "key_findings": [{"finding": "...", "evidence": "...", "importance": "high|medium|low"}],
  "competitor_updates": [{"company": "...", "update": "...", "source": "..."}]
}
```

### Writer (`agents/writer.py`)

**Rôle** : Rédige le rapport final en Markdown + le résumé Discord.

```python
async def writer_node(state: SynState) -> dict:
    """
    Inputs  : state.analysis, state.key_findings, state.competitor_updates
    Outputs : report_title, report_body (Markdown), report_summary

    Le rapport suit un template fixe avec sections obligatoires.
    """
```

Template rapport obligatoire :

```markdown
# {titre} — Veille R&D {date}

## Résumé exécutif

{2-3 phrases d'intro}

## Findings clés

{liste numérotée des key_findings avec importance}

## Analyse détaillée

{analysis complet}

## Mises à jour concurrentes

{competitor_updates sous forme de tableau ou liste}

## Sources

{liste des sources utilisées avec liens si disponibles}

---

_Rapport généré automatiquement par SYN le {datetime}_
```

### Graph (`agents/graph.py`)

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import AsyncRedisSaver

def build_graph():
    graph = StateGraph(SynState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("writer", writer_node)
    graph.add_node("publisher", publisher_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "analyzer")
    graph.add_edge("analyzer", "writer")
    graph.add_edge("writer", "publisher")
    graph.add_edge("publisher", END)

    # Checkpoint Redis pour persistance
    checkpointer = AsyncRedisSaver.from_conn_string("redis://localhost:6379")
    return graph.compile(checkpointer=checkpointer)
```

**Gestion d'erreurs** : chaque node doit catcher ses exceptions, logger
avec loguru, ajouter à `state.errors`, et continuer sans tuer le graph.
Le graph ne doit jamais planter — en cas d'erreur critique, passer
directement à `publisher` avec ce qu'on a.

### Publisher (`agents/publisher.py`)

**Rôle** : Publie le rapport dans Notion + envoie l'alerte Discord.

```python
async def publisher_node(state: SynState) -> dict:
    """
    1. Créer une page dans la database Notion SYN_REPORTS_DB_ID
    2. Envoyer embed Discord via webhook
    3. Sauvegarder le run dans Redis (historique)
    4. Mettre à jour status = "done"
    """
```

**Notion** — créer la page via API REST (pas de SDK) :

```python
POST https://api.notion.com/v1/pages
Headers: Authorization: Bearer {NOTION_TOKEN}, Notion-Version: 2022-06-28
Body:
{
  "parent": {"database_id": NOTION_REPORTS_DB_ID},
  "properties": {
    "Name": {"title": [{"text": {"content": report_title}}]},
    "Date": {"date": {"start": today_iso}},
    "Status": {"select": {"name": "Published"}},
    "Sources": {"multi_select": [...sources]}
  },
  "children": [
    // Convertir le Markdown en blocks Notion
    // Utiliser la fonction markdown_to_notion_blocks()
  ]
}
```

Implémenter `markdown_to_notion_blocks(markdown: str) -> list[dict]` qui
convertit : `#` → heading_1, `##` → heading_2, `###` → heading_3,
`**text**` → bold, `- item` → bulleted_list_item, paragraphes → paragraph.

**Discord** — embed structuré :

```python
{
  "embeds": [{
    "title": report_title,
    "description": report_summary,
    "color": 0x00B4D8,
    "fields": [
      {"name": "Findings clés", "value": top_3_findings, "inline": False},
      {"name": "Sources", "value": sources_count_str, "inline": True},
      {"name": "Rapport complet", "value": f"[Voir dans Notion]({notion_url})", "inline": True}
    ],
    "footer": {"text": f"SYN • {datetime_str}"},
    "timestamp": datetime_iso
  }]
}
```

---

## State persistant Redis

Schéma des clés Redis :

```
syn:runs:{run_id}          → JSON complet du SynState final
syn:runs:history           → Liste JSON des 50 derniers runs [{run_id, date, status, title}]
syn:runs:active            → run_id du run en cours (ou None)
syn:ingestion:last:{query} → timestamp ISO de la dernière ingestion pour cette query
```

TTL : `syn:runs:{run_id}` → 30 jours. `syn:runs:history` → pas de TTL.

---

## Scheduler APScheduler

Fichier : `app/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

def init_scheduler(app):
    """Appelé dans le lifespan FastAPI."""
    # Run quotidien à 7h00 du matin
    scheduler.add_job(
        run_agent_pipeline,
        CronTrigger(hour=7, minute=0),
        id="daily_syn_run",
        replace_existing=True,
    )
    scheduler.start()

async def run_agent_pipeline(run_id: str = None):
    """Lance le graph LangGraph complet."""
    import uuid
    from agents.graph import build_graph
    run_id = run_id or str(uuid.uuid4())
    graph = build_graph()
    initial_state = SynState(run_id=run_id, started_at=datetime.utcnow().isoformat(), ...)
    await graph.ainvoke(initial_state, config={"configurable": {"thread_id": run_id}})
```

---

## Nouveaux fichiers à créer

```
agents/
├── __init__.py
├── state.py         # SynState TypedDict
├── graph.py         # build_graph() — StateGraph complet
├── planner.py       # planner_node()
├── researcher.py    # researcher_node()
├── analyzer.py      # analyzer_node()
├── writer.py        # writer_node()
└── publisher.py     # publisher_node() — Notion + Discord

app/
├── scheduler.py     # APScheduler init + run_agent_pipeline()
└── api/
    └── agent_runs.py  # POST /agents/run, GET /agents/runs, GET /agents/runs/{id}
```

## Fichiers à modifier

- `app/main.py` — inclure router `agent_runs`, init scheduler dans lifespan
- `app/config.py` — ajouter `NOTION_TOKEN`, `NOTION_REPORTS_DB_ID`, `DISCORD_WEBHOOK_URL`
- `requirements.txt` — ajouter nouvelles dépendances

---

## requirements.txt — ajouts Phase 2

```
# Phase 2 additions
langgraph==0.2.55
langchain==0.3.13
langchain-groq==0.2.3
apscheduler==3.10.4
```

---

## Endpoints Phase 2

```
POST /agents/run
Body (optionnel) : {"targets": [...]}  // override manuel du Planner
Response : {"run_id": "uuid", "status": "started"}

GET /agents/runs
Response : {"runs": [{run_id, started_at, status, report_title, duration_seconds}]}

GET /agents/runs/{run_id}
Response : SynState complet depuis Redis
```

---

## Variables .env à ajouter

```
NOTION_TOKEN=secret_...
NOTION_REPORTS_DB_ID=...   # ID de la database Notion où publier les rapports
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
GROQ_API_KEY=gsk_...       # Déjà ajouté Phase 1 — vérifier
```

---

## Règles de qualité (rappel)

- Async partout — `ainvoke`, `astream` sur le graph
- Chaque node catchs ses exceptions → `state.errors` → continue
- Le graph ne plante jamais — fallback vers publisher si erreur critique
- loguru sur chaque node (entrée + sortie + durée)
- Zéro hardcode — tout passe par config.py
- Redis : utiliser `aioredis` (déjà dans les dépendances via `redis[asyncio]`)

---

## Ordre d'exécution

1. `requirements.txt` — ajouter LangGraph, LangChain, APScheduler
2. `agents/state.py` — SynState TypedDict
3. `agents/planner.py` — planner_node
4. `agents/researcher.py` — researcher_node
5. `agents/analyzer.py` — analyzer_node
6. `agents/writer.py` — writer_node
7. `agents/publisher.py` — publisher_node (Notion + Discord)
8. `agents/graph.py` — build_graph() avec checkpointer Redis
9. `app/scheduler.py` — APScheduler
10. `app/api/agent_runs.py` — 3 endpoints
11. `app/main.py` — router + scheduler dans lifespan
12. `app/config.py` — nouvelles variables

---

## Validation Phase 2

```powershell
# 1. Lancer un run manuel
$body = '{}'
Invoke-RestMethod -Uri "http://localhost:8000/agents/run" -Method POST -Body $body -ContentType "application/json"
# → {"run_id": "...", "status": "started"}

# 2. Vérifier le statut (attendre ~30s)
Invoke-RestMethod -Uri "http://localhost:8000/agents/runs/{run_id}"
# → status: "done", report_title: "...", key_findings: [...]

# 3. Historique des runs
Invoke-RestMethod -Uri "http://localhost:8000/agents/runs"

# 4. Redis — vérifier la persistance
docker exec syn-redis redis-cli KEYS "syn:runs:*"

# 5. Vérifier le rapport Notion créé + l'alerte Discord reçue (vérification manuelle)
```
