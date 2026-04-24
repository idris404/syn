import re
import uuid
from dataclasses import dataclass, field

from loguru import logger

SECTION_PATTERNS = {
    "abstract": re.compile(r"(?i)^(abstract|summary|résumé)"),
    "methods": re.compile(r"(?i)^(methods?|materials?\s+and\s+methods?|methodology|patients?\s+and\s+methods?)"),
    "results": re.compile(r"(?i)^(results?|findings?|outcomes?)"),
    "discussion": re.compile(r"(?i)^(discussion|conclusions?|conclusion\s+and\s+discussion)"),
}


@dataclass
class PdfChunk:
    text: str
    page: int
    chunk_index: int
    section: str
    filename: str
    total_chunks: int = 0
    upload_id: str = ""


def _detect_section(line: str, current: str) -> str:
    stripped = line.strip()
    for section, pattern in SECTION_PATTERNS.items():
        if pattern.match(stripped):
            return section
    return current


def _clean_text(text: str) -> str:
    # Normalise whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if end < len(words):
            last_period = chunk.rfind(". ", len(chunk) - 300)
            if last_period > 0:
                chunk = chunk[: last_period + 1]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def parse_pdf(file_bytes: bytes, filename: str, upload_id: str) -> list[PdfChunk]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF not installed") from e

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    all_chunks: list[PdfChunk] = []
    current_section = "other"

    for page_num, page in enumerate(doc):
        raw = page.get_text("text")
        if not raw.strip():
            # fallback to pdfplumber
            try:
                import io
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as plumber:
                    plumber_page = plumber.pages[page_num]
                    raw = plumber_page.extract_text() or ""
            except Exception:
                pass

        cleaned = _clean_text(raw)
        if not cleaned:
            continue

        # Section detection per line
        for line in cleaned.split("\n"):
            current_section = _detect_section(line, current_section)

        chunks = chunk_text(cleaned)
        for chunk_text_part in chunks:
            all_chunks.append(
                PdfChunk(
                    text=chunk_text_part,
                    page=page_num,
                    chunk_index=len(all_chunks),
                    section=current_section,
                    filename=filename,
                    upload_id=upload_id,
                )
            )

    doc.close()

    total = len(all_chunks)
    for chunk in all_chunks:
        chunk.total_chunks = total

    logger.info(f"PDF parsed: {filename} — {len(doc_pages(file_bytes))} pages, {total} chunks")
    return all_chunks


def doc_pages(file_bytes: bytes) -> list:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = list(doc)
    doc.close()
    return pages


def chunk_id(filename: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pdf:{filename}:{chunk_index}"))
