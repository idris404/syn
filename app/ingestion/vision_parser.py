"""
Vision AI pipeline for scientific PDF figure extraction and interpretation.

Pipeline:
  PDF bytes → page images (PyMuPDF) → figure page detection (heuristic)
  → base64 encode → Vision LLM (Anthropic claude-opus-4-5 or OpenAI GPT-4o)
  → structured JSON interpretation → Qdrant + PostgreSQL
"""
import asyncio
import base64
import json
import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO

import httpx
import fitz  # PyMuPDF
from loguru import logger

from app.config import settings

# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class PageImage:
    page_num: int          # 1-indexed
    image_base64: str
    width: int
    height: int
    text_density: float    # words / pixel area
    has_images: bool
    page_text: str = ""


@dataclass
class FigureInterpretation:
    page_num: int
    figure_index: int      # within this PDF session
    figure_type: str
    confidence: float
    raw_interpretation: str
    structured_data: dict = field(default_factory=dict)
    image_base64: str = ""


# ── Vision prompt ──────────────────────────────────────────────────────────

_VISION_PROMPT = """\
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
{{
  "figure_type": "kaplan_meier",
  "confidence": 0.85,
  "raw_interpretation": "Description complète en français...",
  "structured_data": {{}}
}}
"""


# ── Step 1 : PDF → page images ────────────────────────────────────────────

def pdf_to_images(file_bytes: bytes, dpi: int | None = None) -> list[PageImage]:
    """Convert each PDF page to a base64 PNG image."""
    dpi = dpi or settings.vision_dpi
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    results: list[PageImage] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode()

        text = page.get_text()
        word_count = len(text.split())
        area = pix.width * pix.height
        text_density = word_count / area if area > 0 else 0.0

        has_images = len(page.get_images(full=False)) > 0

        results.append(
            PageImage(
                page_num=page_num + 1,
                image_base64=img_b64,
                width=pix.width,
                height=pix.height,
                text_density=text_density,
                has_images=has_images,
                page_text=text[:500],
            )
        )

    doc.close()
    return results


# ── Step 2 : Detect figure pages ──────────────────────────────────────────

def detect_figure_pages(pages: list[PageImage], max_pages: int | None = None) -> list[PageImage]:
    """
    Heuristic: page likely contains a figure if:
      - has_images == True  OR
      - text_density < 0.0003 (little text = space for visuals)
    Skip near-empty pages (text_density < 0.0001 AND no images).
    Limit: max_pages (default settings.vision_max_figures_per_pdf).
    """
    max_pages = max_pages or settings.vision_max_figures_per_pdf
    figure_pages = []

    for page in pages:
        # Skip near-empty non-image pages (likely blank/separator)
        if page.text_density < 0.0001 and not page.has_images:
            continue
        if page.has_images or page.text_density < 0.0003:
            figure_pages.append(page)

    return figure_pages[:max_pages]


# ── Step 3 : Vision LLM providers ─────────────────────────────────────────

async def call_groq_vision(image_base64: str, prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": "llama-3.2-90b-vision-preview",
                "max_tokens": 1500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        },
                        {"type": "text", "text": prompt}
                    ]
                }]
            },
            timeout=60.0
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_openai_vision(image_base64: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
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
                        {"type": "text", "text": prompt},
                    ],
                }],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_vision_llm(image_base64: str, page_context: str) -> str:
    """Route to the configured Vision provider (groq → openai fallback)."""
    prompt = _VISION_PROMPT.format(page_context=page_context[:400] if page_context else "Non disponible")

    provider = settings.vision_provider.lower()
    if provider == "groq" and settings.groq_api_key:
        return await call_groq_vision(image_base64, prompt)
    elif provider == "openai" and settings.openai_api_key:
        return await call_openai_vision(image_base64, prompt)
    elif settings.groq_api_key:
        return await call_groq_vision(image_base64, prompt)
    elif settings.openai_api_key:
        return await call_openai_vision(image_base64, prompt)
    else:
        raise ValueError("No Vision API key configured. Set GROQ_API_KEY or OPENAI_API_KEY.")


# ── Step 4 : Parse Vision response ────────────────────────────────────────

def parse_vision_response(raw: str) -> dict:
    """Parse JSON from Vision LLM response, handle markdown code blocks."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Vision response JSON invalide — fallback minimal")
        return {
            "figure_type": "unknown",
            "confidence": 0.1,
            "raw_interpretation": raw[:2000],
            "structured_data": {},
        }


# ── Step 5 : Interpret a single page ──────────────────────────────────────

async def interpret_figure(page: PageImage, figure_index: int) -> FigureInterpretation:
    """Send a page image to the Vision LLM and return a structured interpretation."""
    logger.debug(f"[Vision] interpreting page={page.page_num} index={figure_index}")
    try:
        raw = await call_vision_llm(
            image_base64=page.image_base64,
            page_context=page.page_text,
        )
        parsed = parse_vision_response(raw)
        return FigureInterpretation(
            page_num=page.page_num,
            figure_index=figure_index,
            figure_type=parsed.get("figure_type", "unknown"),
            confidence=float(parsed.get("confidence", 0.0)),
            raw_interpretation=parsed.get("raw_interpretation", raw[:2000]),
            structured_data=parsed.get("structured_data", {}),
            image_base64=page.image_base64,
        )
    except Exception as e:
        logger.error(f"[Vision] interpret_figure error page={page.page_num}: {e}")
        return FigureInterpretation(
            page_num=page.page_num,
            figure_index=figure_index,
            figure_type="unknown",
            confidence=0.0,
            raw_interpretation=f"Erreur d'interprétation: {e}",
            structured_data={},
            image_base64=page.image_base64,
        )


# ── Full pipeline ──────────────────────────────────────────────────────────

async def run_vision_pipeline(
    file_bytes: bytes,
    upload_id: str,
    concurrency: int = 2,
) -> tuple[list[PageImage], list[FigureInterpretation]]:
    """
    Full pipeline: PDF bytes → page images → detect figures → interpret (async).
    Returns (all_pages, interpretations).
    Concurrency limited to 2 parallel Vision API calls to respect rate limits.
    """
    all_pages = pdf_to_images(file_bytes)
    figure_pages = detect_figure_pages(all_pages)

    logger.info(
        f"[Vision] upload_id={upload_id} total_pages={len(all_pages)} "
        f"figure_pages_detected={len(figure_pages)}"
    )

    if not figure_pages:
        return all_pages, []

    # Groq vision preview has a low rate limit → process sequentially with sleep.
    # Other providers use semaphore-limited concurrency.
    interpretations: list[FigureInterpretation] = []
    use_groq = settings.vision_provider.lower() == "groq" and settings.groq_api_key

    if use_groq:
        for idx, page in enumerate(figure_pages):
            interp = await interpret_figure(page, idx)
            interpretations.append(interp)
            if idx < len(figure_pages) - 1:
                logger.debug("[Vision] sleeping 2s between Groq calls (rate limit)")
                await asyncio.sleep(2)
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def _interpret(page: PageImage, idx: int) -> FigureInterpretation:
            async with semaphore:
                return await interpret_figure(page, idx)

        tasks = [_interpret(page, i) for i, page in enumerate(figure_pages)]
        interpretations = list(await asyncio.gather(*tasks))

    logger.info(f"[Vision] done — {len(interpretations)} figures interpreted")
    return all_pages, interpretations


# ── Helper: figure UUID ────────────────────────────────────────────────────

def figure_uuid(upload_id: str, page_num: int, figure_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"figure:{upload_id}:{page_num}:{figure_index}"))
