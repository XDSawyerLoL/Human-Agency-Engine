from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PaymentIntentCapability(Base):
    __tablename__ = "payment_intent_capabilities"
    __table_args__ = (
        UniqueConstraint("settlement_permit_id", name="uq_payment_intent_parent_settlement_permit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    settlement_permit_id: Mapped[int] = mapped_column(
        ForeignKey("pseudonymous_settlement_permits.id", ondelete="CASCADE"), index=True
    )
    signing_identity_id: Mapped[int] = mapped_column(
        ForeignKey("agent_signing_identities.id", ondelete="CASCADE"), index=True
    )
    capability_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    audience: Mapped[str] = mapped_column(String(128), index=True)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    payment_terms_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
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


class PaymentIntentCapabilityUse(Base):
    __tablename__ = "payment_intent_capability_uses"
    __table_args__ = (
        UniqueConstraint("capability_db_id", "request_id", name="uq_payment_intent_capability_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    capability_db_id: Mapped[int] = mapped_column(
        ForeignKey("payment_intent_capabilities.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    audience: Mapped[str] = mapped_column(String(128), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
