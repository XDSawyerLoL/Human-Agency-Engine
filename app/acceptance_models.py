from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveAllocationDecision(Base):
    __tablename__ = "collective_allocation_decisions"
    __table_args__ = (
        UniqueConstraint("private_allocation_id", name="uq_collective_private_allocation_decision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    private_allocation_id: Mapped[int] = mapped_column(
        ForeignKey("collective_private_allocations.id", ondelete="CASCADE"), index=True
    )
    commitment_id: Mapped[int] = mapped_column(
        ForeignKey("collective_conditional_commitments.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(24), index=True)
    allocation_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    offer_hash: Mapped[str] = mapped_column(String(80), index=True)
    conditions_hash: Mapped[str] = mapped_column(String(80), index=True)
    envelope_hash: Mapped[str] = mapped_column(String(80), index=True)
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    exact_total_amount: Mapped[float] = mapped_column(Float)
    decision_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
