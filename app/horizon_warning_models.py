from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonEarlyWarningEpisode(Base):
    __tablename__ = "horizon_early_warning_episodes"
    __table_args__ = (
        UniqueConstraint("episode_key", name="uq_horizon_early_warning_episode_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_global_events.id", ondelete="CASCADE"), index=True
    )
    pattern_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_behavior_patterns.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(24), default="live", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    current_band: Mapped[str] = mapped_column(String(32), default="emerging", index=True)
    current_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonEarlyWarningSnapshot(Base):
    __tablename__ = "horizon_early_warning_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_key", name="uq_horizon_early_warning_snapshot_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("horizon_early_warning_episodes.id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    input_hash: Mapped[str] = mapped_column(String(96), index=True)
    signal_families: Mapped[list] = mapped_column(JSON, default=list)
    family_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    convergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    convergence_band: Mapped[str] = mapped_column(String(32), index=True)
    cascade_stage: Mapped[str] = mapped_column(String(255), default="")
    expected_onset_low: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_onset_high: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remaining_lead_low_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_lead_high_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    interpretation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
