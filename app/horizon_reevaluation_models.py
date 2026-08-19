from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonReevaluationDecision(Base):
    __tablename__ = "horizon_reevaluation_decisions"
    __table_args__ = (
        UniqueConstraint("decision_key", name="uq_horizon_reevaluation_decision_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    input_hash: Mapped[str] = mapped_column(String(96), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("horizon_personal_impact_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_status: Mapped[str] = mapped_column(String(24), default="unscoped", index=True)
    attention_score: Mapped[float] = mapped_column(Float, default=0.0)
    attention_band: Mapped[str] = mapped_column(String(24), default="silent", index=True)
    cascade_stage: Mapped[str] = mapped_column(String(255), default="")
    surface_requested: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
