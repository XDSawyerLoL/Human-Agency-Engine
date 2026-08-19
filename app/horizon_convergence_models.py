from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonConvergenceSnapshot(Base):
    __tablename__ = "horizon_convergence_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_key", name="uq_horizon_convergence_snapshot_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True
    )
    engine_version: Mapped[str] = mapped_column(String(96), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    independent_sources: Mapped[int] = mapped_column(Integer, default=0)
    source_classes: Mapped[list] = mapped_column(JSON, default=list)
    evidence_roles: Mapped[list] = mapped_column(JSON, default=list)
    convergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
