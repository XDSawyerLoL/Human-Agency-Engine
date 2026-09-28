from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class SoftwareAgentRun(Base):
    __tablename__ = "software_agent_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_software_agent_run_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    adapter_preflight_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_preflights.id", ondelete="CASCADE"),
        index=True,
    )
    adapter_manifest_id: Mapped[int] = mapped_column(
        ForeignKey("execution_adapter_manifests.id"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), default="openhands-agent-server")
    repository: Mapped[str] = mapped_column(String(255), index=True)
    workspace_path: Mapped[str] = mapped_column(String(1024))
    goal_hash: Mapped[str] = mapped_column(String(80), index=True)
    quality_commands: Mapped[list] = mapped_column(JSON, default=list)
    max_iterations: Mapped[int] = mapped_column(Integer)
    worktree_required: Mapped[bool] = mapped_column(Boolean, default=True)
    external_dispatch: Mapped[bool] = mapped_column(Boolean, default=False)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="launching", index=True)
    execution_status: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    final_response_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
