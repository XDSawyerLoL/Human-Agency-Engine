from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PseudonymousSettlementPermit(Base):
    __tablename__ = "pseudonymous_settlement_permits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    settlement_receipt_id: Mapped[int] = mapped_column(
        ForeignKey("collective_settlement_readiness_receipts.id", ondelete="CASCADE"), index=True
    )
    private_allocation_id: Mapped[int] = mapped_column(
        ForeignKey("collective_private_allocations.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("collective_allocation_decisions.id", ondelete="CASCADE"), index=True
    )
    signing_identity_id: Mapped[int] = mapped_column(
        ForeignKey("agent_signing_identities.id", ondelete="CASCADE"), index=True
    )
    permit_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    audience: Mapped[str] = mapped_column(String(96), index=True)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    readiness_hash: Mapped[str] = mapped_column(String(80), index=True)
    allocation_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    accepted_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    offer_hash: Mapped[str] = mapped_column(String(80), index=True)
    decision_hash: Mapped[str] = mapped_column(String(80), index=True)
    conditions_hash: Mapped[str] = mapped_column(String(80), index=True)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    exact_total_amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class SettlementPermitUse(Base):
    __tablename__ = "settlement_permit_uses"
    __table_args__ = (
        UniqueConstraint("permit_db_id", "request_id", name="uq_settlement_permit_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    permit_db_id: Mapped[int] = mapped_column(
        ForeignKey("pseudonymous_settlement_permits.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    audience: Mapped[str] = mapped_column(String(96), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
