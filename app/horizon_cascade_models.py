from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonBehaviorCascade(Base):
    __tablename__ = "horizon_behavior_cascades"
    __table_args__ = (
        UniqueConstraint("cascade_key", name="uq_horizon_behavior_cascade_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cascade_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="live", index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    stage_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    evidence_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    current_stage_index: Mapped[float] = mapped_column(Float, default=0.0)
    current_stage: Mapped[str] = mapped_column(String(255), default="latent")
    next_stage: Mapped[str] = mapped_column(String(255), default="")
    propagation_score: Mapped[float] = mapped_column(Float, default=0.0)
    acceleration_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_diversity_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_band: Mapped[str] = mapped_column(String(24), default="weak", index=True)
    probability_basis: Mapped[str] = mapped_column(String(64), default="not_calibrated")
    interpretation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
