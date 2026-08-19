from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonProvisionalForecast(Base):
    __tablename__ = "horizon_provisional_forecasts"
    __table_args__ = (
        UniqueConstraint("forecast_key", name="uq_horizon_provisional_forecast_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_event_candidates.id", ondelete="CASCADE"), index=True
    )
    pattern_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    fact_status: Mapped[str] = mapped_column(String(40), default="unconfirmed_emerging_event", index=True)
    candidate_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    pattern_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    source_classes: Mapped[list] = mapped_column(JSON, default=list)
    corroboration_score: Mapped[float] = mapped_column(Float, default=0.0)
    provisional_score: Mapped[float] = mapped_column(Float, default=0.0)
    hypothesis_band: Mapped[str] = mapped_column(String(32), default="watch", index=True)
    predicted_response: Mapped[str] = mapped_column(Text, default="")
    probability_basis: Mapped[str] = mapped_column(String(64), default="not_calibrated")
    geography_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    user_surface_allowed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    external_action_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    interpretation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonProvisionalResolution(Base):
    __tablename__ = "horizon_provisional_resolutions"
    __table_args__ = (
        UniqueConstraint("forecast_id", name="uq_horizon_provisional_resolution_forecast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_provisional_forecasts.id", ondelete="CASCADE"), unique=True, index=True
    )
    resolution_type: Mapped[str] = mapped_column(String(32), index=True)
    promoted_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    corroborated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    corroboration_lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    predictive_lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
