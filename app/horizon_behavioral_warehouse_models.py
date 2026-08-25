from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonBehavioralIngestionRun(Base):
    __tablename__ = "horizon_behavioral_ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    query: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), index=True, default="running")
    documents_seen: Mapped[int] = mapped_column(Integer, default=0)
    documents_created: Mapped[int] = mapped_column(Integer, default=0)
    documents_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonBehavioralDocument(Base):
    __tablename__ = "horizon_behavioral_documents"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_horizon_behavioral_document_source_record"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(48), index=True)
    source_record_id: Mapped[str] = mapped_column(String(512), index=True)
    doi: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    work_type: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_access: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    discovery_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    abstract_available: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    ingestion_count: Mapped[int] = mapped_column(Integer, default=1)
    evidence_status: Mapped[str] = mapped_column(String(32), index=True, default="discovered")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonBehavioralEffect(Base):
    __tablename__ = "horizon_behavioral_effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    effect_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavioral_documents.id"), index=True)
    mechanism: Mapped[str] = mapped_column(String(48), index=True)
    construct: Mapped[str] = mapped_column(String(160), index=True)
    population: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    exposure: Mapped[str] = mapped_column(Text)
    behavioral_outcome: Mapped[str] = mapped_column(Text)
    effect_direction: Mapped[str] = mapped_column(String(32), index=True)
    effect_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    effect_size_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uncertainty_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    study_design: Mapped[str] = mapped_column(String(64), index=True)
    replication_status: Mapped[str] = mapped_column(String(32), index=True, default="unknown")
    preregistered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    peer_reviewed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    countries: Mapped[list] = mapped_column(JSON, default=list)
    time_horizon: Mapped[str | None] = mapped_column(String(160), nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text)
    source_locator: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), index=True)
    extraction_version: Mapped[str | None] = mapped_column(String(96), nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    evidence_status: Mapped[str] = mapped_column(String(32), index=True, default="candidate")
    review_notes: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
