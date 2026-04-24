import uuid
from functools import lru_cache

from loguru import logger
from sentence_transformers import SentenceTransformer
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trial import ClinicalTrial
from app.schemas.trial import TrialCreate, TrialResponse
from app.services import qdrant_service


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    logger.info(f"Loading embedding model: {settings.embedding_model}")
    return SentenceTransformer(settings.embedding_model)


def _build_embedding_text(trial: TrialCreate) -> str:
    intervention_names = [i.get("name", "") for i in trial.interventions if i.get("name")]
    parts = [trial.title or ""] + list(trial.conditions) + intervention_names + [trial.sponsor or ""]
    return " | ".join(p for p in parts if p)


def _embed(text: str) -> list[float]:
    model = get_embedding_model()
    return model.encode(text).tolist()


async def upsert_trial(session: AsyncSession, trial: TrialCreate) -> tuple[str, bool]:
    trial_id = uuid.uuid5(uuid.NAMESPACE_URL, trial.nct_id)
    qdrant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"qdrant:{trial.nct_id}")

    values = {
        "id": trial_id,
        "nct_id": trial.nct_id,
        "title": trial.title,
        "status": trial.status,
        "phase": trial.phase,
        "sponsor": trial.sponsor,
        "conditions": trial.conditions,
        "interventions": trial.interventions,
        "primary_outcomes": trial.primary_outcomes,
        "enrollment": trial.enrollment,
        "start_date": trial.start_date,
        "completion_date": trial.completion_date,
        "raw_data": trial.raw_data,
        "qdrant_id": qdrant_id,
    }

    stmt = (
        insert(ClinicalTrial)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["nct_id"],
            set_={k: v for k, v in values.items() if k not in ("id", "nct_id")},
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    was_inserted = result.rowcount == 1

    embedding_text = _build_embedding_text(trial)
    vector = _embed(embedding_text)
    await qdrant_service.upsert_trial(
        qdrant_id=qdrant_id,
        vector=vector,
        nct_id=trial.nct_id,
        title=trial.title,
        status=trial.status,
        phase=trial.phase,
        sponsor=trial.sponsor,
    )

    return trial.nct_id, was_inserted


async def search_trials_hybrid(
    session: AsyncSession,
    query: str,
    phase: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[TrialResponse]:
    vector = _embed(query)
    qdrant_results = await qdrant_service.search_trials(vector, limit=limit * 2)

    if not qdrant_results:
        return []

    nct_ids = [nct_id for nct_id, _ in qdrant_results]
    score_map = {nct_id: score for nct_id, score in qdrant_results}

    stmt = select(ClinicalTrial).where(ClinicalTrial.nct_id.in_(nct_ids))
    if phase:
        stmt = stmt.where(ClinicalTrial.phase == phase)
    if status:
        stmt = stmt.where(ClinicalTrial.status == status)

    db_results = await session.execute(stmt)
    trials = db_results.scalars().all()

    responses = []
    for trial in trials:
        response = TrialResponse.model_validate(trial)
        response.semantic_score = score_map.get(trial.nct_id)
        responses.append(response)

    responses.sort(key=lambda r: r.semantic_score or 0, reverse=True)
    return responses[:limit]


async def get_by_nct_id(session: AsyncSession, nct_id: str) -> TrialResponse | None:
    stmt = select(ClinicalTrial).where(ClinicalTrial.nct_id == nct_id)
    result = await session.execute(stmt)
    trial = result.scalar_one_or_none()
    if trial is None:
        return None
    return TrialResponse.model_validate(trial)
