from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class WorldEvent(Base):
    __tablename__ = "world_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    subject_type: Mapped[str] = mapped_column(String(64), default="")
    subject_id: Mapped[str] = mapped_column(String(128), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    causation_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    previous_hash: Mapped[str] = mapped_column(String(64), default="")
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class WorldHypothesis(Base):
    __tablename__ = "world_hypotheses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    cause_pattern: Mapped[dict] = mapped_column(JSON, default=dict)
    effect_pattern: Mapped[dict] = mapped_column(JSON, default=dict)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    direction: Mapped[str] = mapped_column(String(24), default="unknown")
    claim_level: Mapped[str] = mapped_column(String(32), default="correlation", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    inconclusive_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("future_scenarios.id"), nullable=True, index=True)
    hypothesis_id: Mapped[int | None] = mapped_column(ForeignKey("world_hypotheses.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    intervention: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_effects: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_conditions: Mapped[list] = mapped_column(JSON, default=list)
    rollback_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    reversible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    authorization_status: Mapped[str] = mapped_column(String(24), default="proposed", index=True)
    execution_status: Mapped[str] = mapped_column(String(24), default="planned", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExperimentObservation(Base):
    __tablename__ = "experiment_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    verdict: Mapped[str] = mapped_column(String(24), default="inconclusive", index=True)
    quality: Mapped[float] = mapped_column(Float, default=0.5)
    notes: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[int] = mapped_column(ForeignKey("world_hypotheses.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("world_events.id"), nullable=True, index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True, index=True)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_observations.id"), nullable=True, index=True)
    verdict: Mapped[str] = mapped_column(String(24), index=True)
    quality: Mapped[float] = mapped_column(Float, default=0.5)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
