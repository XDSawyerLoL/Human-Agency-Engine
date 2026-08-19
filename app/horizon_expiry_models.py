from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonForecastExpiry(Base):
    __tablename__ = "horizon_forecast_expiries"
    __table_args__ = (
        UniqueConstraint("forecast_id", name="uq_horizon_forecast_expiry_forecast"),
        UniqueConstraint("expiry_key", name="uq_horizon_forecast_expiry_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expiry_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_forecasts.id", ondelete="CASCADE"), unique=True, index=True
    )
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True)
    expected_onset_high: Mapped[datetime] = mapped_column(DateTime, index=True)
    grace_hours: Mapped[float] = mapped_column(Float, default=24.0)
    expiry_deadline: Mapped[datetime] = mapped_column(DateTime, index=True)
    expired_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    checked_materialization_signal_types: Mapped[list] = mapped_column(JSON, default=list)
    rule_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
