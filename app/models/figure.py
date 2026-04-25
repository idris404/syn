import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FigureRecord(Base):
    __tablename__ = "figure_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    upload_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    paper_nct_id: Mapped[str | None] = mapped_column(String, nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    figure_index: Mapped[int] = mapped_column(Integer, nullable=False)
    figure_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="unknown",
    )  # kaplan_meier | forest_plot | bar_chart | table | scatter | unknown
    raw_interpretation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    qdrant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_figure_records_upload_figure", "upload_id", "figure_index"),
    )
