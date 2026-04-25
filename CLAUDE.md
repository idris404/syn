# SYN — Phase 4 : Dashboard Next.js

## État actuel du projet (Phases 0 + 1 + 2 + 3 complètes)

Lis tout le code existant avant de toucher quoi que ce soit.

**Infrastructure** : PostgreSQL 5433, Qdrant 6333, Redis 6379
**Backend FastAPI** opérationnel sur port 8000 avec :

- `/trials/*` — essais ClinicalTrials
- `/papers/*`, `/figures/*` — publications et figures
- `/ingest/*` — ingestion (trials, pubmed, biorxiv, ema, pdf, pdf/vision)
- `/rag/query` — RAG Groq llama-3.3-70b
- `/agents/run`, `/agents/runs` — pipeline LangGraph autonome
- Vision AI : Groq llama-3.2-90b-vision-preview
  **Collections Qdrant** : syn_trials, syn_papers, syn_ema, syn_figures
  **Models PG** : ClinicalTrial, PaperRecord, FigureRecord
  **Biopython absent** — PubMed via httpx + xml.etree, ne pas changer

---

## Objectif Phase 4

Construire le dashboard Next.js qui consomme le FastAPI existant.
Le dashboard est une **app séparée** dans `frontend/` à la racine du projet.
Ne rien modifier dans `app/` sauf ajouter CORS et 2-3 endpoints WebSocket.

### Deliverables obligatoires

1. Dashboard Next.js 14 App Router + TypeScript
2. Page `/` — vue d'ensemble : KPIs, derniers runs agents, alertes récentes
3. Page `/trials` — liste + recherche sémantique temps réel des essais
4. Page `/trials/[nct_id]` — détail essai + papers associés + figures
5. Page `/reports` — historique des rapports générés par les agents
6. Page `/reports/[run_id]` — rapport complet en Markdown rendu
7. Page `/ingest` — interface d'upload PDF (texte + vision)
8. WebSocket alertes temps réel — nouveau run agent terminé → notification UI
9. Export PDF d'un rapport depuis le dashboard

---

## Structure projet

```
syn/
├── app/                    # FastAPI existant — ne pas toucher sauf CORS + WS
│   └── api/
│       └── ws.py           # NOUVEAU : WebSocket endpoint
├── frontend/               # NOUVEAU : Next.js app
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                    # Dashboard home
│   │   ├── trials/
│   │   │   ├── page.tsx               # Liste essais + search
│   │   │   └── [nct_id]/
│   │   │       └── page.tsx           # Détail essai
│   │   ├── reports/
│   │   │   ├── page.tsx               # Liste rapports
│   │   │   └── [run_id]/
│   │   │       └── page.tsx           # Rapport complet
│   │   └── ingest/
│   │       └── page.tsx               # Upload PDF
│   ├── components/
│   │   ├── ui/                        # shadcn/ui components
│   │   ├── TrialCard.tsx
│   │   ├── TrialSearchBar.tsx
│   │   ├── AgentRunCard.tsx
│   │   ├── ReportViewer.tsx
│   │   ├── FigureGallery.tsx
│   │   ├── KpiCard.tsx
│   │   ├── AlertBanner.tsx
│   │   └── PdfUploader.tsx
│   ├── lib/
│   │   ├── api.ts                     # Fetch wrapper vers FastAPI
│   │   └── types.ts                   # Types TypeScript (miroir des schemas Pydantic)
│   ├── hooks/
│   │   └── useWebSocket.ts            # Hook WebSocket alertes temps réel
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
```

---

## Setup Next.js 15

```bash
# Depuis la racine du projet syn/
cd F:\Work\syn
npx create-next-app@15 frontend --typescript --tailwind --app --no-src-dir --import-alias "@/*"
cd frontend
npx shadcn@latest init
npx shadcn@latest add button card badge input table tabs scroll-area separator skeleton toast
npm install recharts react-markdown remark-gfm lucide-react
```

`next.config.ts` — proxy vers FastAPI pour éviter CORS en dev :

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};
export default nextConfig;
```

Avec ce proxy, le frontend appelle `/api/trials/search` et Next.js
forward vers `http://localhost:8000/trials/search`. Zero CORS à gérer en dev.

**Next.js 15 — breaking changes à respecter partout :**

1. **Params dynamiques sont des Promises** — dans toutes les pages `[nct_id]` et `[run_id]` :

```typescript
// Next.js 15 — params est une Promise, toujours await
export default async function Page({
  params,
}: {
  params: Promise<{ nct_id: string }>;
}) {
  const { nct_id } = await params;
  // ...
}
```

2. **`searchParams` est une Promise** dans les Server Components :

```typescript
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; phase?: string }>;
}) {
  const { q, phase } = await searchParams;
}
```

3. **Turbopack activé par défaut** en dev (`next dev --turbo`). Si un package
   est incompatible, revenir à `next dev` sans flag.

4. **React 19** — `use()` hook disponible pour unwrapper les Promises côté client :

```typescript
"use client";
import { use } from "react";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); // version client avec React 19
}
```

---

## FastAPI — modifications minimales

### CORS (`app/main.py`)

Ajouter avant les routers :

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### WebSocket (`app/api/ws.py`) — NOUVEAU

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
import asyncio, json

router = APIRouter(prefix="/ws", tags=["websocket"])

# Connexions actives
_connections: list[WebSocket] = []

async def broadcast(message: dict):
    """Appelé par publisher.py quand un run est terminé."""
    dead = []
    for ws in _connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.remove(ws)

@router.websocket("/alerts")
async def alerts_ws(websocket: WebSocket):
    await websocket.accept()
    _connections.append(websocket)
    logger.info(f"WebSocket connecté — {len(_connections)} clients actifs")
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _connections.remove(websocket)
        logger.info("WebSocket déconnecté")
```

Dans `agents/publisher.py`, appeler `broadcast()` après publication :

```python
from app.api.ws import broadcast
await broadcast({
    "type": "run_complete",
    "run_id": state["run_id"],
    "title": state["report_title"],
    "summary": state["report_summary"],
    "timestamp": datetime.utcnow().isoformat()
})
```

Ajouter `ws.router` dans `app/main.py`.

---

## Types TypeScript (`frontend/lib/types.ts`)

```typescript
export interface Trial {
  id: string;
  nct_id: string;
  title: string;
  status: string;
  phase: string;
  sponsor: string;
  conditions: string[];
  interventions: Array<{ type: string; name: string }>;
  primary_outcomes: Array<{ measure: string; timeFrame: string }>;
  enrollment: number | null;
  start_date: string | null;
  completion_date: string | null;
}

export interface TrialSearchResult {
  score: number;
  nct_id: string;
  title: string;
  status: string;
  phase: string;
  sponsor: string;
  conditions: string[];
  enrollment: number | null;
  start_date: string | null;
  completion_date: string | null;
}

export interface AgentRun {
  run_id: string;
  started_at: string;
  status:
    | "planning"
    | "researching"
    | "analyzing"
    | "writing"
    | "publishing"
    | "done"
    | "failed";
  report_title: string;
  report_summary: string;
  key_findings: Array<{
    finding: string;
    evidence: string;
    importance: "high" | "medium" | "low";
  }>;
  duration_seconds?: number;
  errors: string[];
}

export interface Figure {
  id: string;
  upload_id: string;
  page_number: number;
  figure_type:
    | "kaplan_meier"
    | "forest_plot"
    | "bar_chart"
    | "table"
    | "scatter"
    | "unknown";
  raw_interpretation: string;
  structured_data: Record<string, unknown>;
  confidence_score: number;
}

export interface KpiData {
  total_trials: number;
  recruiting_trials: number;
  total_papers: number;
  total_reports: number;
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface WsMessage {
  type: "run_complete" | "ping";
  run_id?: string;
  title?: string;
  summary?: string;
  timestamp?: string;
}
```

## API Client (`frontend/lib/api.ts`)

```typescript
const BASE = "/api";

async function get<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params)
    Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  // Trials
  searchTrials: (q: string, phase?: string, status?: string, limit = 20) =>
    get<{ results: TrialSearchResult[] }>("/trials/search", {
      q,
      phase,
      status,
      limit: String(limit),
    }),
  getTrial: (nctId: string) => get<Trial>(`/trials/${nctId}`),
  getTrialPapers: (nctId: string) =>
    get<{ results: unknown[] }>(`/trials/${nctId}/papers`),

  // Figures
  getFigures: (uploadId: string) =>
    get<{ figures: Figure[] }>(`/papers/${uploadId}/figures`),

  // Agent runs
  getRuns: () => get<{ runs: AgentRun[] }>("/agents/runs"),
  getRun: (runId: string) => get<AgentRun>(`/agents/runs/${runId}`),
  triggerRun: () => post<{ run_id: string; status: string }>("/agents/run"),

  // Ingest
  uploadPdf: (file: File, vision = false) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/ingest/pdf${vision ? "/vision" : ""}`, {
      method: "POST",
      body: form,
    }).then((r) => r.json());
  },

  // KPIs — à implémenter dans FastAPI
  getKpis: () => get<KpiData>("/kpis"),
};
```

---

## Endpoint KPI à ajouter dans FastAPI (`app/api/kpis.py`) — NOUVEAU

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.trial import ClinicalTrial
from app.models.paper import PaperRecord
import redis.asyncio as aioredis
from app.config import settings

router = APIRouter(tags=["kpis"])

@router.get("/kpis")
async def get_kpis(db: AsyncSession = Depends(get_db)):
    total_trials = (await db.execute(select(func.count()).select_from(ClinicalTrial))).scalar()
    recruiting = (await db.execute(
        select(func.count()).select_from(ClinicalTrial).where(ClinicalTrial.status == "RECRUITING")
    )).scalar()
    total_papers = (await db.execute(select(func.count()).select_from(PaperRecord))).scalar()

    # Dernière run depuis Redis
    r = aioredis.from_url(settings.redis_url)
    history_raw = await r.get("syn:runs:history")
    await r.aclose()
    last_run = None
    last_run_status = None
    if history_raw:
        import json
        history = json.loads(history_raw)
        if history:
            last_run = history[-1].get("date")
            last_run_status = history[-1].get("status")

    return {
        "total_trials": total_trials,
        "recruiting_trials": recruiting,
        "total_papers": total_papers,
        "total_reports": len(json.loads(history_raw)) if history_raw else 0,
        "last_run_at": last_run,
        "last_run_status": last_run_status,
    }
```

---

## Pages Next.js — spécifications

### `app/page.tsx` — Dashboard home

4 KpiCards en grid : Total Essais, En recrutement, Papers indexés, Rapports générés.
Dernier run agent : titre + status + badge importance.
Bouton "Lancer un run" → `POST /api/agents/run` → toast notification.
AlertBanner si un message WebSocket `run_complete` arrive.

```tsx
// Structure de la page
export default function HomePage() {
  return (
    <main>
      <AlertBanner /> {/* WebSocket alerts */}
      <KpiGrid /> {/* 4 cards */}
      <div className="grid grid-cols-2 gap-6">
        <LastRunCard /> {/* Dernier rapport agent */}
        <QuickActionsCard /> {/* Bouton run + upload */}
      </div>
      <RecentTrialsTable /> {/* 5 derniers essais ingérés */}
    </main>
  );
}
```

### `app/trials/page.tsx` — Recherche essais

SearchBar avec debounce 400ms → appel `/api/trials/search` à chaque frappe.
Filtres : Phase (dropdown), Status (dropdown).
Résultats : cards avec score de similarité, badge status coloré, badge phase.
Click sur un essai → `/trials/[nct_id]`.

```tsx
// Debounce search
const [query, setQuery] = useState("");
const debouncedQuery = useDebounce(query, 400);

useEffect(() => {
  if (debouncedQuery) {
    api.searchTrials(debouncedQuery, phase, status).then(setResults);
  }
}, [debouncedQuery, phase, status]);
```

### `app/trials/[nct_id]/page.tsx` — Détail essai

**Next.js 15 — params async obligatoire :**

```typescript
export default async function TrialPage({
  params,
}: {
  params: Promise<{ nct_id: string }>;
}) {
  const { nct_id } = await params;
  // fetch trial data...
}
```

3 onglets (Tabs shadcn) :

- **Informations** : tous les champs du Trial (conditions, interventions, outcomes, dates, enrollment)
- **Publications** : papers PubMed/bioRxiv associés depuis `/trials/{nct_id}/papers`
- **Figures** : si des figures ont été extraites pour des papers liés, les afficher avec FigureGallery

### `app/reports/page.tsx` — Liste rapports

Table des runs agents : date, titre, status (badge coloré), nb findings, durée.
Bouton "Nouveau rapport" → trigger run → polling statut toutes les 5s jusqu'à `done`.

### `app/reports/[run_id]/page.tsx` — Rapport complet

**Next.js 15 — params async obligatoire :**

```typescript
export default async function ReportPage({
  params,
}: {
  params: Promise<{ run_id: string }>;
}) {
  const { run_id } = await params;
  // fetch run data...
}
```

Afficher `report_body` (Markdown) rendu avec `react-markdown` + `remark-gfm`.
Section findings clés avec badges importance (rouge=high, orange=medium, gris=low).
Bouton "Export PDF" → `window.print()` avec CSS print (le plus simple sans Puppeteer).

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

<ReactMarkdown remarkPlugins={[remarkGfm]}>{run.report_body}</ReactMarkdown>;
```

CSS print pour l'export :

```css
@media print {
  nav,
  button,
  .no-print {
    display: none;
  }
  body {
    font-size: 12pt;
  }
}
```

### `app/ingest/page.tsx` — Upload PDF

Drag & drop zone (ou input file).
Toggle : "Extraction texte" vs "Vision AI (figures)".
Progress bar simulée pendant l'upload (l'API prend 5-30s).
Résultat : nb chunks créés (texte) ou nb figures trouvées (vision) avec leurs types.

### `hooks/useWebSocket.ts`

```typescript
export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/alerts");
    ws.onmessage = (e) => {
      const msg: WsMessage = JSON.parse(e.data);
      if (msg.type !== "ping") onMessage(msg);
    };
    ws.onerror = () => console.warn("WS error — alertes désactivées");
    return () => ws.close();
  }, []);
}
```

---

## Design System

Utiliser **exclusivement** Tailwind + shadcn/ui. Pas d'autre lib CSS.

Palette couleurs SYN :

```typescript
// tailwind.config.ts — extend colors
colors: {
  syn: {
    bg: '#0a0a0f',
    surface: '#12121a',
    border: '#1e1e2e',
    accent: '#00b4d8',
    success: '#22c55e',
    warning: '#f59e0b',
    danger: '#ef4444',
    text: '#e2e8f0',
    muted: '#64748b',
  }
}
```

Dark mode uniquement. Background `syn-bg`, cards `syn-surface`.
Badge status :

- RECRUITING → `bg-green-500/10 text-green-400`
- COMPLETED → `bg-blue-500/10 text-blue-400`
- ACTIVE_NOT_RECRUITING → `bg-yellow-500/10 text-yellow-400`
- Autres → `bg-gray-500/10 text-gray-400`

---

## `FigureGallery` component

```tsx
// components/FigureGallery.tsx
interface Props {
  figures: Figure[];
}

export function FigureGallery({ figures }: Props) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {figures.map((fig) => (
        <div key={fig.id} className="border border-syn-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <Badge>{fig.figure_type.replace("_", " ")}</Badge>
            <span className="text-xs text-syn-muted">
              Confiance : {Math.round(fig.confidence_score * 100)}%
            </span>
          </div>
          <p className="text-sm text-syn-muted">
            {fig.raw_interpretation.slice(0, 300)}...
          </p>
          {/* Données structurées si KM */}
          {fig.figure_type === "kaplan_meier" &&
            fig.structured_data?.hazard_ratio && (
              <div className="mt-2 text-xs font-mono bg-syn-bg p-2 rounded">
                HR = {fig.structured_data.hazard_ratio as number}
                {fig.structured_data.p_value &&
                  ` | p = ${fig.structured_data.p_value}`}
              </div>
            )}
        </div>
      ))}
    </div>
  );
}
```

---

## requirements.txt FastAPI — aucun ajout

Tout est déjà installé. Juste ajouter `ws.py` et `kpis.py`.

## package.json frontend — dépendances

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19",
    "react-dom": "^19",
    "typescript": "^5",
    "tailwindcss": "^3",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0",
    "recharts": "^2.13.3",
    "lucide-react": "^0.460.0"
  }
}
```

shadcn/ui est ajouté via `npx shadcn@latest add`.

---

## Ordre d'exécution

**Backend (modifier FastAPI en premier) :**

1. `app/api/ws.py` — WebSocket endpoint
2. `app/api/kpis.py` — KPI endpoint
3. `app/main.py` — CORS + router ws + router kpis
4. `agents/publisher.py` — appel broadcast() après publication

**Frontend (ensuite) :** 5. Setup Next.js + shadcn (commandes ci-dessus) 6. `frontend/lib/types.ts` — tous les types 7. `frontend/lib/api.ts` — client API 8. `frontend/hooks/useWebSocket.ts` 9. `frontend/components/` — tous les composants (KpiCard, TrialCard, AgentRunCard, FigureGallery, AlertBanner, PdfUploader, ReportViewer) 10. `frontend/app/layout.tsx` — layout principal avec nav 11. `frontend/app/page.tsx` — home dashboard 12. `frontend/app/trials/page.tsx` 13. `frontend/app/trials/[nct_id]/page.tsx` 14. `frontend/app/reports/page.tsx` 15. `frontend/app/reports/[run_id]/page.tsx` 16. `frontend/app/ingest/page.tsx`

---

## Validation Phase 4

```powershell
# 1. FastAPI toujours OK
Invoke-RestMethod -Uri "http://localhost:8000/health"
Invoke-RestMethod -Uri "http://localhost:8000/kpis"

# 2. Lancer le frontend (Next.js 15 — Turbopack par défaut)
cd F:\Work\syn\frontend
npm run dev
# → http://localhost:3000
# Si un package est incompatible Turbopack : npx next dev (sans --turbo)

# 3. Tests manuels dans le browser :
# - http://localhost:3000 → KPIs s'affichent (chiffres réels depuis PG)
# - http://localhost:3000/trials → taper "pembrolizumab" → résultats sémantiques
# - http://localhost:3000/reports → liste des runs agents
# - http://localhost:3000/ingest → upload un PDF → voir les chunks ou figures

# 4. WebSocket test
# Trigger un run depuis l'UI → vérifier que l'AlertBanner apparaît quand done

# 5. Export PDF
# Ouvrir un rapport → bouton Export → Ctrl+P → vérifier mise en page propre
```
