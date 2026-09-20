import io
import uuid
from typing import AsyncGenerator

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

EMA_XLSX_URL = (
    "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
)

COLUMN_MAP = {
    "Name of medicine": "medicine_name",
    "EMA product number": "product_number",
    "Medicine status": "authorisation_status",
    "International non-proprietary name (INN) / common name": "inn",
    "ATC code (human)": "atc_code",
    "First published date": "first_published",
    "Last updated date": "revision_date",
    "Medicine URL": "url",
    "Medicine name": "medicine_name",
    "Active substance": "active_substance",
    "Product number": "product_number",
    "Patient safety": "patient_safety",
    "Authorisation status": "authorisation_status",
    "ATC code": "atc_code",
    "International non-proprietary name (INN)": "inn",
    "First published": "first_published",
    "Revision date": "revision_date",
    "Category": "category",
    "Generic": "generic",
    "Biosimilar": "biosimilar",
    "Orphan medicine": "orphan_medicine",
    "Exceptional circumstances": "exceptional_circumstances",
    "URL": "url",
}


def _as_text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _read_table(raw: bytes) -> pd.DataFrame:
    preview = pd.read_excel(io.BytesIO(raw), header=None, nrows=20, engine="openpyxl")
    header_rows = [
        index
        for index, row in preview.iterrows()
        if "EMA product number" in row.values or "Product number" in row.values
    ]
    if not header_rows:
        raise ValueError("EMA medicine table header not found")
    return pd.read_excel(io.BytesIO(raw), header=header_rows[0], engine="openpyxl")


def _uuid5_product(product_number: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ema:{product_number}"))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _download_xlsx() -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        response = await client.get(EMA_XLSX_URL)
        response.raise_for_status()
        return response.content


async def fetch_medicines() -> AsyncGenerator[dict, None]:
    logger.info("Downloading EMA EPAR Excel file...")
    raw = await _download_xlsx()
    logger.info(f"Downloaded {len(raw):,} bytes — parsing...")

    df = _read_table(raw)

    # Rename known columns
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    if "product_number" not in df or "authorisation_status" not in df:
        raise ValueError("EMA medicine table is missing required columns")

    # Filter authorised only
    if "authorisation_status" in df.columns:
        df = df[df["authorisation_status"].astype(str).str.strip().str.lower() == "authorised"]

    df = df.where(pd.notna(df), None)

    for _, row in df.iterrows():
        product_number = _as_text(row.get("product_number"))
        if not product_number:
            continue

        medicine_name = _as_text(row.get("medicine_name"))
        active_substance = _as_text(row.get("active_substance"))
        inn = _as_text(row.get("inn"))

        record = {
            "id": _uuid5_product(product_number),
            "product_number": product_number,
            "medicine_name": medicine_name,
            "active_substance": active_substance,
            "inn": inn,
            "patient_safety": _as_text(row.get("patient_safety")),
            "authorisation_status": row.get("authorisation_status"),
            "atc_code": _as_text(row.get("atc_code")),
            "first_published": _as_text(row.get("first_published")),
            "revision_date": _as_text(row.get("revision_date")),
            "category": _as_text(row.get("category")),
            "generic": _as_text(row.get("generic")),
            "biosimilar": _as_text(row.get("biosimilar")),
            "orphan_medicine": _as_text(row.get("orphan_medicine")),
            "exceptional_circumstances": _as_text(row.get("exceptional_circumstances")),
            "url": _as_text(row.get("url")),
        }
        yield record

    logger.info("EMA Excel parsing complete.")
