from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ExecutionAdapterManifest(Base):
    __tablename__ = "execution_adapter_manifests"
    __table_args__ = (
        UniqueConstraint("adapter_id", "version", name="uq_execution_adapter_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    adapter_id: Mapped[str] = mapped_column(String(96), index=True)
    version: Mapped[str] = mapped_column(String(32), index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    supported_action_types: Mapped[list] = mapped_column(JSON, default=list)
    reversible_only: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_idempotency: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_rollback: Mapped[bool] = mapped_column(Boolean, default=True)
    side_effect_free_preflight: Mapped[bool] = mapped_column(Boolean, default=True)
    external_dispatch_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    contract_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AdapterPreflight(Base):
    __tablename__ = "adapter_preflights"
    __table_args__ = (
        UniqueConstraint("adapter_manifest_id", "idempotency_key", name="uq_adapter_preflight_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    dry_run_id: Mapped[int] = mapped_column(ForeignKey("execution_dry_runs.id", ondelete="CASCADE"), index=True)
    adapter_manifest_id: Mapped[int] = mapped_column(ForeignKey("execution_adapter_manifests.id"), index=True)
    preflight_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    action_type: Mapped[str] = mapped_column(String(96), index=True)
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    adapter_contract_hash: Mapped[str] = mapped_column(String(80), index=True)
    rollback_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="contract_compatible", index=True)
    external_probe_performed: Mapped[bool] = mapped_column(Boolean, default=False)
    external_dispatch: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
