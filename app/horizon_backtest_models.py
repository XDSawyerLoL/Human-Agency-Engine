from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonHistoricalBacktestRun(Base):
    __tablename__ = "horizon_historical_backtest_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_horizon_historical_backtest_run_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    engine_version: Mapped[str] = mapped_column(String(96), index=True)
    requested_start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    evaluation_as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    max_events: Mapped[int] = mapped_column(Integer, default=250)
    max_cases: Mapped[int] = mapped_column(Integer, default=2000)
    dataset_fingerprint: Mapped[str] = mapped_column(String(96), index=True)
    selected_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    selected_forecast_ids: Mapped[list] = mapped_column(JSON, default=list)
    excluded_collateral_forecast_ids: Mapped[list] = mapped_column(JSON, default=list)
    case_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
