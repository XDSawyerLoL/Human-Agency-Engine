from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonCollectorLease(Base):
    __tablename__ = "horizon_collector_leases"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonCollectorSourceState(Base):
    __tablename__ = "horizon_collector_source_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    cadence_seconds: Mapped[int] = mapped_column(Integer)
    next_due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_result: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonCollectorCycle(Base):
    __tablename__ = "horizon_collector_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="worker", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    due_sources: Mapped[list] = mapped_column(JSON, default=list)
    source_results: Mapped[list] = mapped_column(JSON, default=list)
    postprocessing: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
