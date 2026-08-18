from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ExecutionReadinessReceipt(Base):
    __tablename__ = "execution_readiness_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    preflight_id: Mapped[int] = mapped_column(ForeignKey("adapter_preflights.id", ondelete="CASCADE"), index=True)
    attestation_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_sandbox_attestations.id"), nullable=True, index=True)
    policy_receipt_id: Mapped[int | None] = mapped_column(ForeignKey("policy_receipts.id", ondelete="SET NULL"), nullable=True, index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    adapter_contract_hash: Mapped[str] = mapped_column(String(80), index=True)
    attestation_evidence_hash: Mapped[str] = mapped_column(String(80), default="", index=True)
    decision: Mapped[str] = mapped_column(String(40), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    external_dispatch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
