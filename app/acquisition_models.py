from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class InformationNeed(Base):
    __tablename__ = "information_needs"
    __table_args__ = (
        UniqueConstraint("user_id", "need_key", name="uq_information_need_user_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_interventions.id"), nullable=True, index=True)
    future_run_id: Mapped[int | None] = mapped_column(ForeignKey("future_runs.id"), nullable=True, index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("future_scenarios.id"), nullable=True, index=True)
    need_key: Mapped[str] = mapped_column(String(64), index=True)
    need_type: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    acquisition_mode: Mapped[str] = mapped_column(String(32), default="read_only_then_user", index=True)
    preferred_sources: Mapped[list] = mapped_column(JSON, default=list)
    sensitivity: Mapped[str] = mapped_column(String(32), default="personal", index=True)
    blocks_candidate: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution_source: Mapped[str] = mapped_column(String(64), default="")
    resolution_provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ask_count: Mapped[int] = mapped_column(Integer, default=0)
    last_asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
