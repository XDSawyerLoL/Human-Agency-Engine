from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CandidateIntervention(Base):
    __tablename__ = "candidate_interventions"
    __table_args__ = (
        UniqueConstraint("user_id", "candidate_key", name="uq_candidate_user_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    candidate_key: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_ref: Mapped[str] = mapped_column(String(128), default="", index=True)
    source_opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    hypothesis_ids: Mapped[list] = mapped_column(JSON, default=list)
    intent_ids: Mapped[list] = mapped_column(JSON, default=list)
    name: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str] = mapped_column(Text, default="")
    intervention: Mapped[dict] = mapped_column(JSON, default=dict)
    effects: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="generated", index=True)
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    future_run_id: Mapped[int | None] = mapped_column(ForeignKey("future_runs.id"), nullable=True, index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("future_scenarios.id"), nullable=True, index=True)
    decision_status: Mapped[str] = mapped_column(String(64), default="", index=True)
    surfaced_opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
