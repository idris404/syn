import asyncio
from typing import AsyncGenerator

import httpx
from dateutil import parser as dateparser
from loguru import logger
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.schemas.trial import TrialCreate

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return dateparser.parse(date_str).date()
    except Exception:
        return None


def _extract_trial(study: dict) -> TrialCreate | None:
    try:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        conditions_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        outcomes_mod = proto.get("outcomesModule", {})

        nct_id = ident.get("nctId")
        if not nct_id:
            return None

        phases = design.get("phases", [])
        phase = phases[0] if phases else None

        interventions = [
            {"type": i.get("type"), "name": i.get("name")}
            for i in arms_mod.get("interventions", [])
        ]
        primary_outcomes = [
            {"measure": o.get("measure"), "timeFrame": o.get("timeFrame")}
            for o in outcomes_mod.get("primaryOutcomes", [])
        ]

        start_date_str = status_mod.get("startDateStruct", {}).get("date")
        completion_date_str = status_mod.get("primaryCompletionDateStruct", {}).get("date")

        enrollment_info = design.get("enrollmentInfo", {})
        enrollment = enrollment_info.get("count")

        return TrialCreate(
            nct_id=nct_id,
            title=ident.get("briefTitle"),
            status=status_mod.get("overallStatus"),
            phase=phase,
            sponsor=sponsor_mod.get("leadSponsor", {}).get("name"),
            conditions=conditions_mod.get("conditions", []),
            interventions=interventions,
            primary_outcomes=primary_outcomes,
            enrollment=enrollment,
            start_date=_parse_date(start_date_str),
            completion_date=_parse_date(completion_date_str),
            raw_data=study,
        )
    except Exception as e:
        logger.warning(f"Failed to parse study: {e}")
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _fetch_page(client: httpx.AsyncClient, params: dict) -> dict:
    response = await client.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


async def fetch_trials(query: str, max_results: int = 100) -> AsyncGenerator[TrialCreate, None]:
    params = {
        "query.term": query,
        "pageSize": 50,
        "format": "json",
    }
    fetched = 0

    async with httpx.AsyncClient(headers=REQUEST_HEADERS) as client:
        while fetched < max_results:
            try:
                data = await _fetch_page(client, params)
            except RetryError as e:
                logger.error(f"ClinicalTrials.gov fetch failed after retries for query='{query}': {e}")
                return

            studies = data.get("studies", [])

            if not studies:
                break

            for study in studies:
                if fetched >= max_results:
                    return
                trial = _extract_trial(study)
                if trial:
                    yield trial
                    fetched += 1

            next_token = data.get("nextPageToken")
            if not next_token:
                break

            params["pageToken"] = next_token
            await asyncio.sleep(0.35)
