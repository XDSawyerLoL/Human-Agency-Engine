from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonGlobalEvent(Base):
    __tablename__ = "horizon_global_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    geography: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(96), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_reliability: Mapped[float] = mapped_column(Float, default=0.5)
    raw_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonSocialSignal(Base):
    __tablename__ = "horizon_social_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    signal_key: Mapped[str] = mapped_column(String(192), unique=True, index=True)
    signal_type: Mapped[str] = mapped_column(String(96), index=True)
    source: Mapped[str] = mapped_column(String(96), index=True)
    geography: Mapped[list] = mapped_column(JSON, default=list)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    reliability: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HorizonBehaviorPattern(Base):
    __tablename__ = "horizon_behavior_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    required_signal_types: Mapped[list] = mapped_column(JSON, default=list)
    predicted_response: Mapped[str] = mapped_column(Text)
    mechanism_chain: Mapped[list] = mapped_column(JSON, default=list)
    expected_lag_hours_low: Mapped[int] = mapped_column(Integer, default=0)
    expected_lag_hours_high: Mapped[int] = mapped_column(Integer, default=168)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    knowledge_available_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HorizonForecast(Base):
    __tablename__ = "horizon_forecasts"
    __table_args__ = (
        UniqueConstraint("forecast_key", name="uq_horizon_forecast_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id"), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="live", index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_facts_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    social_signal_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    personal_exposure: Mapped[dict] = mapped_column(JSON, default=dict)
    behavior_chain: Mapped[list] = mapped_column(JSON, default=list)
    predicted_outcome: Mapped[str] = mapped_column(Text)
    likelihood_band: Mapped[str] = mapped_column(String(24), index=True)
    predictive_score: Mapped[float] = mapped_column(Float, default=0.0)
    probability_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_mid: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_basis: Mapped[str] = mapped_column(String(64), default="not_calibrated")
    expected_onset_low: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_onset_high: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_window: Mapped[dict] = mapped_column(JSON, default=dict)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    calibration_status: Mapped[str] = mapped_column(String(32), default="uncalibrated", index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonForecastResolution(Base):
    __tablename__ = "horizon_forecast_resolutions"
    __table_args__ = (
        UniqueConstraint("forecast_id", name="uq_horizon_resolution_forecast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("horizon_forecasts.id", ondelete="CASCADE"), unique=True, index=True)
    outcome_occurred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_summary: Mapped[str] = mapped_column(Text, default="")
    correctness: Mapped[str] = mapped_column(String(24), default="inconclusive", index=True)
    became_obvious_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    personal_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    predictive_lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actionable_lead_time_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
