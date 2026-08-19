from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonWeatherImpactChain(Base):
    __tablename__ = "horizon_weather_impact_chains"
    __table_args__ = (
        UniqueConstraint("chain_key", name="uq_horizon_weather_impact_chain_key"),
        UniqueConstraint("provisional_forecast_id", name="uq_horizon_weather_impact_chain_forecast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    provisional_forecast_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_provisional_forecasts.id", ondelete="CASCADE"), unique=True, index=True
    )
    provisional_resolution_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_provisional_resolutions.id", ondelete="CASCADE"), index=True
    )
    windy_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_event_candidates.id", ondelete="CASCADE"), index=True
    )
    confirmed_event_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True
    )
    regional_event_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True
    )
    outcome_signal_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_social_signals.id", ondelete="CASCADE"), index=True
    )
    windy_first_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    official_confirmed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    behavior_observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    windy_to_official_lead_hours: Mapped[float] = mapped_column(Float)
    official_to_behavior_lag_hours: Mapped[float] = mapped_column(Float)
    windy_to_behavior_lead_hours: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
