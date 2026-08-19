from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonLiveSource(Base):
    __tablename__ = "horizon_live_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    source_kind: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True, index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HorizonLiveIngestionRecord(Base):
    __tablename__ = "horizon_live_ingestion_records"
    __table_args__ = (
        UniqueConstraint(
            "source_key",
            "external_key",
            "payload_hash",
            name="uq_horizon_live_source_external_payload",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(96), index=True)
    external_key: Mapped[str] = mapped_column(String(192), index=True)
    payload_hash: Mapped[str] = mapped_column(String(80), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True
    )
    provider_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
