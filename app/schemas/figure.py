import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FigureResponse(BaseModel):
    id: str
    upload_id: str
    paper_nct_id: str | None = None
    page_number: int
    figure_index: int
    figure_type: str
    raw_interpretation: str
    structured_data: dict = Field(default_factory=dict)
    confidence_score: float
    qdrant_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class FigureSummary(BaseModel):
    """Compact summary used in upload response."""
    page: int
    figure_index: int
    figure_type: str
    confidence: float
    summary: str   # first 200 chars of raw_interpretation
    figure_id: str


class VisionIngestResponse(BaseModel):
    upload_id: str
    filename: str
    pages_analyzed: int
    figures_found: int
    figures: list[FigureSummary]
    duration_seconds: float
    vision_provider: str
