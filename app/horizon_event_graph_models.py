from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HorizonEventGraphSnapshot(Base):
    __tablename__ = "horizon_event_graph_snapshots"
    __table_args__ = (UniqueConstraint("graph_key", name="uq_horizon_event_graph_snapshot_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    graph_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    engine_version: Mapped[str] = mapped_column(String(96), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    episode_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
