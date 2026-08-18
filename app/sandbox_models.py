from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class SandboxRunnerIdentity(Base):
    __tablename__ = "sandbox_runner_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    runner_id: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    public_key_b64: Mapped[str] = mapped_column(String(128))
    key_fingerprint: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class AdapterSandboxAttestation(Base):
    __tablename__ = "adapter_sandbox_attestations"
    __table_args__ = (
        UniqueConstraint("runner_identity_id", "runner_run_id", name="uq_sandbox_runner_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    adapter_manifest_id: Mapped[int] = mapped_column(ForeignKey("execution_adapter_manifests.id"), index=True)
    runner_identity_id: Mapped[int] = mapped_column(ForeignKey("sandbox_runner_identities.id"), index=True)
    attestation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    runner_run_id: Mapped[str] = mapped_column(String(128), index=True)
    suite_version: Mapped[str] = mapped_column(String(64), index=True)
    adapter_contract_hash: Mapped[str] = mapped_column(String(80), index=True)
    evidence_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    signature_b64: Mapped[str] = mapped_column(Text)
    initial_state_hash: Mapped[str] = mapped_column(String(80))
    post_preflight_state_hash: Mapped[str] = mapped_column(String(80))
    first_result_hash: Mapped[str] = mapped_column(String(80))
    repeat_result_hash: Mapped[str] = mapped_column(String(80))
    post_first_state_hash: Mapped[str] = mapped_column(String(80))
    post_repeat_state_hash: Mapped[str] = mapped_column(String(80))
    partial_failure_before_hash: Mapped[str] = mapped_column(String(80))
    partial_failure_after_hash: Mapped[str] = mapped_column(String(80))
    rollback_state_hash: Mapped[str] = mapped_column(String(80))
    preflight_no_side_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    partial_failure_safe: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_restored: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="failed", index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
