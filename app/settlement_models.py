from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveSettlementReadinessReceipt(Base):
    __tablename__ = "collective_settlement_readiness_receipts"
    __table_args__ = (
        UniqueConstraint(
            "allocation_round_id",
            "accepted_set_hash",
            name="uq_collective_settlement_allocation_acceptance_set",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_db_id: Mapped[int] = mapped_column(
        ForeignKey("collective_market_offers.id", ondelete="CASCADE"), index=True
    )
    allocation_round_id: Mapped[int] = mapped_column(
        ForeignKey("collective_allocation_rounds.id", ondelete="CASCADE"), index=True
    )
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    allocation_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    commitment_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    accepted_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    accepted_user_count: Mapped[int] = mapped_column(Integer)
    accepted_quantity: Mapped[int] = mapped_column(Integer)
    allocated_user_count: Mapped[int] = mapped_column(Integer)
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    exact_total_amount: Mapped[float] = mapped_column(Float)
    minimum_anonymity_set: Mapped[int] = mapped_column(Integer, default=10)
    all_allocated_users_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    commercial_minimum_met: Mapped[bool] = mapped_column(Boolean, default=False)
    capacity_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    settlement_ready: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    external_dispatch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_created: Mapped[bool] = mapped_column(Boolean, default=False)
    order_created: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
