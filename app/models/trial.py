import uuid
from datetime import date, datetime

from sqlalchemy import UUID, Date, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClinicalTrial(Base):
    __tablename__ = "clinical_trials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nct_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sponsor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conditions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    interventions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    primary_outcomes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    qdrant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_clinical_trials_nct_id", "nct_id"),
        Index("ix_clinical_trials_status", "status"),
        Index("ix_clinical_trials_phase", "phase"),
        Index("ix_clinical_trials_sponsor", "sponsor"),
    )
