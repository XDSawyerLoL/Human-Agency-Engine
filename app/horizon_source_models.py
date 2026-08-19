from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonSource(Base):
    __tablename__ = "horizon_sources"
    __table_args__ = (UniqueConstraint("source_key", name="uq_horizon_source_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_class: Mapped[str] = mapped_column(String(48), index=True)
    adapter_kind: Mapped[str] = mapped_column(String(64), index=True)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    geography: Mapped[list] = mapped_column(JSON, default=list)
    base_locator: Mapped[str] = mapped_column(Text, default="")
    trust_weight: Mapped[float] = mapped_column(Float, default=0.5)
    refresh_seconds: Mapped[int] = mapped_column(Integer, default=900)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HorizonRawObservation(Base):
    __tablename__ = "horizon_raw_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "external_key", name="uq_horizon_observation_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("horizon_sources.id", ondelete="CASCADE"), index=True)
    external_key: Mapped[str] = mapped_column(String(192), index=True)
    observation_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    geography: Mapped[list] = mapped_column(JSON, default=list)
    canonical_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(80), index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HorizonEventCandidate(Base):
    __tablename__ = "horizon_event_candidates"
    __table_args__ = (UniqueConstraint("candidate_key", name="uq_horizon_event_candidate_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    title: Mapped[str] = mapped_column(String(255))
    geography: Mapped[list] = mapped_column(JSON, default=list)
    corroborating_observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_classes: Mapped[list] = mapped_column(JSON, default=list)
    corroboration_score: Mapped[float] = mapped_column(Float, default=0.0)
    promotion_status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    promoted_event_id: Mapped[int | None] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="SET NULL"), nullable=True, index=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
