import io
import uuid
from typing import AsyncGenerator

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

EMA_XLSX_URL = (
    "https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx"
)

COLUMN_MAP = {
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

    df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")

    # Rename known columns
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Filter authorised only
    if "authorisation_status" in df.columns:
        df = df[df["authorisation_status"].str.strip().str.lower() == "authorised"]

    df = df.where(pd.notna(df), None)

    for _, row in df.iterrows():
        product_number = str(row.get("product_number") or "").strip()
        if not product_number:
            continue

        medicine_name = str(row.get("medicine_name") or "").strip()
        active_substance = str(row.get("active_substance") or "").strip()
        inn = str(row.get("inn") or "").strip()

        record = {
            "id": _uuid5_product(product_number),
            "product_number": product_number,
            "medicine_name": medicine_name,
            "active_substance": active_substance,
            "inn": inn,
            "patient_safety": row.get("patient_safety"),
            "authorisation_status": row.get("authorisation_status"),
            "atc_code": row.get("atc_code"),
            "first_published": str(row.get("first_published") or ""),
            "revision_date": str(row.get("revision_date") or ""),
            "category": row.get("category"),
            "generic": row.get("generic"),
            "biosimilar": row.get("biosimilar"),
            "orphan_medicine": row.get("orphan_medicine"),
            "exceptional_circumstances": row.get("exceptional_circumstances"),
            "url": row.get("url"),
        }
        yield record

    logger.info("EMA Excel parsing complete.")
