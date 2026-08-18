from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PolicyReceipt(Base):
    __tablename__ = "policy_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    engine_version: Mapped[str] = mapped_column(String(64), index=True)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    capability: Mapped[str] = mapped_column(String(32), index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    evaluated_constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    receipt_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HumanCommitAuthorization(Base):
    __tablename__ = "human_commit_authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    policy_receipt_id: Mapped[int] = mapped_column(ForeignKey("policy_receipts.id", ondelete="CASCADE"), index=True)
    commit_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    action_type: Mapped[str] = mapped_column(String(96), default="")
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    exact_action: Mapped[dict] = mapped_column(JSON, default=dict)
    rollback_plan: Mapped[str] = mapped_column(Text)
    rollback_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    token_hash: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="prepared", index=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class ExecutionDryRun(Base):
    __tablename__ = "execution_dry_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("delegation_grants.id", ondelete="CASCADE"), index=True)
    human_commit_id: Mapped[int] = mapped_column(ForeignKey("human_commit_authorizations.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="authorized_dry_run", index=True)
    would_execute: Mapped[bool] = mapped_column(Boolean, default=False)
    external_dispatch: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
