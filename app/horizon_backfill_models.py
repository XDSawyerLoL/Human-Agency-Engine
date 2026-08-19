from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonHistoricalCoverageInterval(Base):
    __tablename__ = "horizon_historical_coverage_intervals"
    __table_args__ = (
        UniqueConstraint("coverage_key", name="uq_horizon_historical_coverage_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coverage_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_sources.id", ondelete="CASCADE"), index=True
    )
    coverage_kind: Mapped[str] = mapped_column(String(32), index=True)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    signal_types: Mapped[list] = mapped_column(JSON, default=list)
    geography: Mapped[list] = mapped_column(JSON, default=list)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    completeness: Mapped[str] = mapped_column(String(24), default="partial", index=True)
    basis: Mapped[str] = mapped_column(String(64), default="", index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonHistoricalBackfillRun(Base):
    __tablename__ = "horizon_historical_backfill_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_horizon_historical_backfill_run_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    engine_version: Mapped[str] = mapped_column(String(96), index=True)
    adapter_kind: Mapped[str] = mapped_column(String(96), index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_sources.id", ondelete="CASCADE"), index=True
    )
    requested_start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
