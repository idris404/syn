import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class InterventionSchema(BaseModel):
    type: str | None = None
    name: str | None = None


class PrimaryOutcomeSchema(BaseModel):
    measure: str | None = None
    timeFrame: str | None = None


class TrialCreate(BaseModel):
    nct_id: str
    title: str | None = None
    status: str | None = None
    phase: str | None = None
    sponsor: str | None = None
    conditions: list[str] = Field(default_factory=list)
    interventions: list[dict] = Field(default_factory=list)
    primary_outcomes: list[dict] = Field(default_factory=list)
    enrollment: int | None = None
    start_date: date | None = None
    completion_date: date | None = None
    raw_data: dict | None = None


class TrialResponse(BaseModel):
    id: uuid.UUID
    nct_id: str
    title: str | None
    status: str | None
    phase: str | None
    sponsor: str | None
    conditions: list | None
    interventions: list | None
    primary_outcomes: list | None
    enrollment: int | None
    start_date: date | None
    completion_date: date | None
    qdrant_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    semantic_score: float | None = None

    model_config = {"from_attributes": True}


class TrialSearchParams(BaseModel):
    q: str
    phase: str | None = None
    status: str | None = None
    limit: int = 20


class IngestReport(BaseModel):
    query: str
    total_fetched: int
    inserted: int
    updated: int
    skipped: int
    errors: int
    duration_seconds: float


class TrialSearchResponse(BaseModel):
    query: str
    count: int
    results: list[TrialResponse]
