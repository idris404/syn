# SYN — Phase 3 : Vision AI sur PDFs scientifiques

## État actuel du projet (Phases 0 + 1 + 2 complètes)

Lis tout le code existant avant de toucher quoi que ce soit.

**Infrastructure** : PostgreSQL 5433, Qdrant 6333, Redis 6379
**Agents** : Planner → Researcher → Analyzer → Writer → Publisher (LangGraph + MemorySaver)
**RAG** : retrieve() multi-collection + generate() Groq llama-3.3-70b
**PDF** : PyMuPDF + pdfplumber, chunking 400 mots/50 overlap, `POST /ingest/pdf`
**Collections Qdrant** : syn_trials, syn_papers, syn_ema
**Biopython absent** — PubMed via httpx + xml.etree, ne pas changer

---

## Objectif Phase 3

Ajouter la compréhension **visuelle** des PDFs scientifiques complexes.
Un paper de Phase III contient des courbes Kaplan-Meier, forest plots,
tableaux de résultats avec p-values/HR/CI que le texte seul ne capture pas.

Le pipeline Vision AI extrait ces figures, les fait interpréter par un LLM
multimodal, structure les résultats cliniques, et les intègre dans le RAG
existant pour que l'Analyzer puisse les exploiter.

### Deliverables obligatoires

1. `POST /ingest/pdf/vision` — PDF → extraction figures → interprétation Vision LLM → Qdrant
2. `GET /papers/{upload_id}/figures` — liste des figures extraites avec leurs interprétations
3. Intégration dans l'Analyzer (Phase 2) — les findings visuels enrichissent l'analyse
4. `FigureRecord` model PostgreSQL — métadonnées des figures extraites
5. Collection Qdrant `syn_figures` — figures vectorisées (texte de l'interprétation)

---

## Architecture Vision AI

### Pipeline complet

```
PDF uploadé
    ↓
Extraction pages → images PNG (PyMuPDF fitz)
    ↓
Détection figures (heuristique : pages avec peu de texte + présence d'images)
    ↓
Crop des figures (bounding boxes via pdfplumber ou fitz)
    ↓
Encodage base64
    ↓
Vision LLM (Claude claude-opus-4-5 vision OU GPT-4o selon dispo)
    ↓
Réponse structurée JSON : type + données extraites + interprétation
    ↓
Upsert Qdrant syn_figures (texte interprétation vectorisé)
    ↓
Upsert PostgreSQL FigureRecord (métadonnées + base64 thumbnail)
```

---

## Nouveaux fichiers à créer

```
app/
├── ingestion/
│   └── vision_parser.py      # Pipeline Vision AI complet
├── models/
│   └── figure.py             # FigureRecord SQLAlchemy model
├── schemas/
│   └── figure.py             # Pydantic schemas figures
└── api/
    └── figures.py            # GET /papers/{upload_id}/figures
                              # POST /ingest/pdf/vision
```

## Fichiers à modifier

- `app/services/qdrant_service.py` — ajouter `upsert_figure()`, `search_figures()`
- `app/main.py` — inclure router `figures`
- `app/config.py` — ajouter `VISION_MODEL`, `VISION_PROVIDER`, `ANTHROPIC_API_KEY`
- `agents/analyzer.py` — enrichir avec les findings visuels
- `requirements.txt` — ajouter `anthropic`, `Pillow`

---

## Spécifications techniques détaillées

### `FigureRecord` model (`app/models/figure.py`)

```python
class FigureRecord(Base):
    __tablename__ = "figure_records"

    id: UUID PK (uuid5 sur upload_id + page + figure_index)
    upload_id: str INDEX           # lien vers le PDF parent
    paper_nct_id: Optional[str]    # si associé à un essai clinique
    page_number: int
    figure_index: int              # index de la figure dans la page
    figure_type: str               # "kaplan_meier" | "forest_plot" | "bar_chart"
                                   # | "table" | "scatter" | "unknown"
    raw_interpretation: str        # réponse texte brute du LLM vision
    structured_data: JSONB         # données extraites structurées (voir specs)
    confidence_score: float        # 0.0 à 1.0 — auto-évaluation du LLM
    image_base64: Optional[str]    # thumbnail PNG base64 pour le dashboard
    qdrant_id: Optional[UUID]
    created_at: datetime
```

Générer + appliquer la migration Alembic après création.

### `vision_parser.py` — Pipeline complet

#### Étape 1 : Extraction pages → images

```python
import fitz  # PyMuPDF

def pdf_to_images(pdf_path: str, dpi: int = 150) -> list[dict]:
    """
    Convertit chaque page PDF en image PNG base64.
    dpi=150 : bon compromis qualité/taille (éviter 300 qui dépasse les limites Vision API).
    Retourne : [{page_num, image_base64, width, height, text_density}]
    text_density = nb_mots / (width * height) — utile pour détecter les pages "figure-heavy"
    """
    doc = fitz.open(pdf_path)
    results = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode()
        text = page.get_text()
        word_count = len(text.split())
        area = pix.width * pix.height
        results.append({
            "page_num": page_num + 1,
            "image_base64": img_b64,
            "width": pix.width,
            "height": pix.height,
            "text_density": word_count / area if area > 0 else 0,
            "has_images": len(page.get_images()) > 0,
        })
    return results
```

#### Étape 2 : Détection pages avec figures

```python
def detect_figure_pages(pages: list[dict]) -> list[dict]:
    """
    Heuristique : page contient probablement une figure si :
    - has_images == True  OU
    - text_density < 0.0003 (peu de texte = espace occupé par des visuels)
    Ne pas analyser toutes les pages — trop coûteux en tokens Vision.
    Limite : max 10 pages par PDF.
    """
```

#### Étape 3 : Interprétation Vision LLM

```python
async def interpret_figure(image_base64: str, page_context: str = "") -> dict:
    """
    Envoie l'image au LLM Vision et récupère une interprétation structurée.
    Utilise Anthropic Claude si VISION_PROVIDER="anthropic", OpenAI sinon.
    """
```

**Prompt Vision (critique — ne pas simplifier)** :

```
Tu es un expert en analyse de données cliniques et biomédicales.
Analyse cette figure extraite d'un paper scientifique de Phase II/III.

Contexte de la page : {page_context}

Instructions :
1. Identifie le TYPE de figure parmi : kaplan_meier, forest_plot, bar_chart,
   table, scatter_plot, box_plot, flow_diagram, unknown
2. Extrait les DONNÉES NUMÉRIQUES visibles (valeurs, axes, légendes)
3. Interprète les RÉSULTATS CLINIQUES avec précision
4. Évalue ta CONFIANCE dans l'interprétation (0.0 à 1.0)

Si c'est une courbe Kaplan-Meier, extrait :
- Les groupes comparés (ex: traitement vs placebo)
- La médiane de survie de chaque groupe
- Le p-value si visible
- Le Hazard Ratio (HR) et son intervalle de confiance si visible
- L'endpoint (OS, PFS, DFS, etc.)

Si c'est un forest plot, extrait :
- La liste des sous-groupes
- HR et CI 95% de chaque sous-groupe
- L'effet global
- Le sens de l'effet (faveur traitement ou contrôle)

Si c'est un tableau, extrait :
- Les en-têtes de colonnes
- Les valeurs numériques clés
- Les p-values si présentes

Réponds UNIQUEMENT en JSON valide :
{
  "figure_type": "kaplan_meier",
  "confidence": 0.85,
  "raw_interpretation": "Description complète en français...",
  "structured_data": {
    // Pour kaplan_meier :
    "endpoint": "PFS",
    "groups": [
      {"name": "Pembrolizumab", "median_months": 12.3, "ci_95": [10.1, 14.5]},
      {"name": "Placebo", "median_months": 6.1, "ci_95": [4.8, 7.4]}
    ],
    "hazard_ratio": 0.58,
    "hr_ci_95": [0.43, 0.78],
    "p_value": 0.0001,
    "n_patients": 432
    // Adapter selon le type de figure
  }
}
```

#### Étape 4 : Appel API Vision

**Provider Anthropic** (préféré) :

```python
import anthropic

async def call_anthropic_vision(image_base64: str, prompt: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-opus-4-5",  # vision capable
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": prompt}
            ],
        }]
    )
    return message.content[0].text
```

**Provider OpenAI** (fallback si VISION_PROVIDER="openai") :

```python
import httpx

async def call_openai_vision(image_base64: str, prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "gpt-4o",
                "max_tokens": 1500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            },
            timeout=60.0
        )
        return resp.json()["choices"][0]["message"]["content"]
```

#### Étape 5 : Parsing JSON robuste

````python
def parse_vision_response(raw: str) -> dict:
    """
    Parse la réponse JSON du LLM vision.
    Gère les cas où le LLM entoure le JSON de backticks markdown.
    """
    import re
    # Strip markdown code blocks si présents
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback : retourner une structure minimale
        logger.warning(f"Vision response JSON invalide, fallback minimal")
        return {
            "figure_type": "unknown",
            "confidence": 0.1,
            "raw_interpretation": raw,
            "structured_data": {}
        }
````

### Endpoint `POST /ingest/pdf/vision`

```python
@router.post("/pdf/vision")
async def ingest_pdf_vision(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    nct_id: str = Form(default=""),   # optionnel — associe au bon essai
    db: AsyncSession = Depends(get_db),
):
    """
    Upload PDF → extrait les figures → Vision LLM → Qdrant + PostgreSQL.
    Retourne le rapport d'ingestion avec les figures trouvées.
    """
```

Réponse :

```json
{
  "upload_id": "uuid4",
  "filename": "KEYNOTE-189-results.pdf",
  "pages_analyzed": 8,
  "figures_found": 4,
  "figures": [
    {
      "page": 3,
      "figure_type": "kaplan_meier",
      "confidence": 0.91,
      "summary": "Courbe KM PFS pembrolizumab vs placebo — HR 0.58 (p<0.0001)",
      "figure_id": "uuid"
    }
  ],
  "duration_seconds": 18.3,
  "vision_provider": "anthropic"
}
```

**Limite de sécurité** : max 10 figures analysées par PDF (coût tokens).
Si plus de 10 pages détectées comme figures, prendre les 10 premières.

### Endpoint `GET /papers/{upload_id}/figures`

```python
@router.get("/{upload_id}/figures")
async def get_figures(upload_id: str, db: AsyncSession = Depends(get_db)):
    """Retourne toutes les figures extraites d'un PDF avec leurs interprétations."""
```

### Collection Qdrant `syn_figures`

Texte vectorisé = `raw_interpretation` (texte complet de l'interprétation).
Payload :

```python
{
    "upload_id": str,
    "figure_type": str,
    "confidence": float,
    "paper_nct_id": str,
    "page_number": int,
    "endpoint": str,        # si KM : "PFS", "OS", etc.
    "hr": float,            # si disponible
    "p_value": float,       # si disponible
}
```

Ajouter dans `qdrant_service.py` :

- `ensure_collections()` — ajouter `syn_figures`
- `upsert_figure(figure_id, text, payload)`
- `search_figures(query, filters, limit)`

### Intégration dans l'Analyzer (Phase 2)

Modifier `agents/analyzer.py` pour inclure les données visuelles :

```python
async def analyzer_node(state: SynState) -> dict:
    # ... code existant ...

    # NOUVEAU : Récupérer les findings visuels pertinents
    visual_findings = await qdrant_service.search_figures(
        query=state.targets[0]["query"] if state.targets else "",
        limit=5
    )

    # Enrichir le contexte envoyé à Groq avec les données visuelles
    visual_context = ""
    if visual_findings:
        visual_context = "\n\nDonnées visuelles extraites (courbes, forest plots) :\n"
        for fig in visual_findings:
            payload = fig.get("payload", {})
            visual_context += f"- {payload.get('figure_type', 'figure')} "
            if payload.get('hr'):
                visual_context += f"HR={payload['hr']} "
            if payload.get('p_value'):
                visual_context += f"p={payload['p_value']} "
            visual_context += f"— {fig.get('raw_interpretation', '')[:200]}\n"

    # Inclure visual_context dans le prompt Groq de l'Analyzer
```

---

## Variables .env à ajouter

```
# Vision AI
VISION_PROVIDER=anthropic          # "anthropic" ou "openai"
ANTHROPIC_API_KEY=sk-ant-...       # Si VISION_PROVIDER=anthropic
# OPENAI_API_KEY déjà présent si besoin du fallback OpenAI

# Limites Vision
VISION_MAX_FIGURES_PER_PDF=10
VISION_DPI=150
```

Ajouter dans `config.py` :

```python
vision_provider: str = "anthropic"
anthropic_api_key: str = ""
vision_max_figures_per_pdf: int = 10
vision_dpi: int = 150
```

---

## requirements.txt — ajouts Phase 3

```
# Phase 3 additions
anthropic==0.40.0
Pillow==11.0.0
```

PyMuPDF et pdfplumber sont déjà installés (Phase 1).

---

## Ordre d'exécution

1. `requirements.txt` — ajouter anthropic, Pillow
2. `app/config.py` — nouvelles variables Vision
3. `.env` — ajouter ANTHROPIC_API_KEY + VISION_PROVIDER
4. `app/models/figure.py` — FigureRecord model
5. Migration Alembic — générer + appliquer
6. `app/schemas/figure.py` — Pydantic schemas
7. `app/services/qdrant_service.py` — upsert_figure, search_figures, syn_figures collection
8. `app/ingestion/vision_parser.py` — pipeline complet
9. `app/api/figures.py` — endpoints
10. `app/api/ingest.py` — ajouter POST /ingest/pdf/vision
11. `app/main.py` — router figures
12. `agents/analyzer.py` — enrichissement visuel

---

## Validation Phase 3

```powershell
# 1. Upload un PDF scientifique (paper Phase III avec des figures)
# Télécharge un paper ClinicalTrials avec des résultats d'essais
# ex: https://www.nejm.org/doi/full/10.1056/NEJMoa1501824 (KEYNOTE-006)
# ou n'importe quel PDF de paper avec courbes KM

$pdf = Get-Item "path\to\paper.pdf"
$form = @{ file = $pdf; title = "KEYNOTE paper test"; nct_id = "" }
Invoke-RestMethod -Uri "http://localhost:8000/ingest/pdf/vision" -Method POST -Form $form
# → figures_found > 0, figure_type = "kaplan_meier" ou "forest_plot"

# 2. Récupérer les figures extraites
Invoke-RestMethod -Uri "http://localhost:8000/papers/{upload_id}/figures"

# 3. Recherche sémantique sur les figures
Invoke-RestMethod -Uri "http://localhost:8000/papers/search?q=hazard+ratio+survival&limit=5"

# 4. Vérifier PostgreSQL
docker exec syn-postgres psql -U syn -d syn -c "SELECT figure_type, confidence, page_number FROM figure_records LIMIT 10;"

# 5. Lancer un run agent complet et vérifier que les visual_findings apparaissent
$body = '{}'
Invoke-RestMethod -Uri "http://localhost:8000/agents/run" -Method POST -Body $body -ContentType "application/json"
# Vérifier dans les logs que l'Analyzer mentionne "Données visuelles extraites"
```

## Notes importantes

**Coût tokens** : Vision LLM coûte cher. 1 page PDF à 150 DPI ≈ 500-800 tokens
image. 10 figures × 800 tokens = ~8000 tokens image + prompt par PDF.
Avec claude-opus-4-5 : ~0.04$ par PDF. Acceptable pour un side project.

**Timeout** : mettre timeout=120s sur les appels Vision — l'analyse d'une
image complexe peut prendre 15-20s.

**Qualité des PDFs** : les PDFs scannés (images de pages) fonctionnent
moins bien que les PDFs natifs (texte sélectionnable). Ajouter un check
`if text_density < 0.0001 and not has_images: skip_page()`.
