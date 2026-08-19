from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonPersonalImpactAssessment(Base):
    __tablename__ = "horizon_personal_impact_assessments"
    __table_args__ = (
        UniqueConstraint("assessment_key", name="uq_horizon_personal_impact_assessment_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("horizon_forecasts.id", ondelete="CASCADE"), index=True)
    cascade_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_cascades.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="live", index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    fact_layer: Mapped[dict] = mapped_column(JSON, default=dict)
    collective_behavior_layer: Mapped[dict] = mapped_column(JSON, default=dict)
    personal_exposure_layer: Mapped[dict] = mapped_column(JSON, default=dict)
    timing_layer: Mapped[dict] = mapped_column(JSON, default=dict)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0)
    attention_score: Mapped[float] = mapped_column(Float, default=0.0)
    attention_band: Mapped[str] = mapped_column(String(24), default="silent", index=True)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
