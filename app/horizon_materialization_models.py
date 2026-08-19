from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonMaterializationDetection(Base):
    __tablename__ = "horizon_materialization_detections"
    __table_args__ = (
        UniqueConstraint("detection_key", name="uq_horizon_materialization_detection_key"),
        UniqueConstraint("forecast_id", name="uq_horizon_materialization_forecast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    detection_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_forecasts.id", ondelete="CASCADE"), unique=True, index=True
    )
    event_id: Mapped[int] = mapped_column(ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True)
    became_obvious_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    predictive_lead_time_hours: Mapped[float] = mapped_column(Float)
    evidence_signal_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_sources: Mapped[list] = mapped_column(JSON, default=list)
    materialization_signal_types: Mapped[list] = mapped_column(JSON, default=list)
    rule_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
