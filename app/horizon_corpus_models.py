from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonCalibrationCorpusRun(Base):
    __tablename__ = "horizon_calibration_corpus_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    corpus_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    engine_version: Mapped[str] = mapped_column(String(96), index=True)
    requested_start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    slice_days: Mapped[int] = mapped_column(Integer)
    outcome_grace_days: Mapped[int] = mapped_column(Integer)
    request_snapshot: Mapped[dict] = mapped_column(JSON)
    summary_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HorizonCalibrationCorpusSlice(Base):
    __tablename__ = "horizon_calibration_corpus_slices"
    __table_args__ = (
        UniqueConstraint("run_id", "slice_index", name="uq_horizon_calibration_corpus_run_slice"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slice_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("horizon_calibration_corpus_runs.id"), index=True)
    slice_index: Mapped[int] = mapped_column(Integer, index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    evaluation_as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    meteo_result: Mapped[dict] = mapped_column(JSON, default=dict)
    rte_result: Mapped[dict] = mapped_column(JSON, default=dict)
    backtest_result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
