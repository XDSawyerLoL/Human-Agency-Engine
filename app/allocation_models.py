from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveAllocationRound(Base):
    __tablename__ = "collective_allocation_rounds"
    __table_args__ = (
        UniqueConstraint("offer_db_id", "commitment_set_hash", name="uq_collective_offer_commitment_set_allocation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_db_id: Mapped[int] = mapped_column(ForeignKey("collective_market_offers.id", ondelete="CASCADE"), index=True)
    allocation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    commitment_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    seed_hash: Mapped[str] = mapped_column(String(80), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(64), index=True)
    committed_user_count: Mapped[int] = mapped_column(Integer)
    committed_quantity: Mapped[int] = mapped_column(Integer)
    capacity_quantity: Mapped[int] = mapped_column(Integer)
    allocated_user_count: Mapped[int] = mapped_column(Integer)
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    oversubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    allocation_set_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="allocated", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CollectivePrivateAllocation(Base):
    __tablename__ = "collective_private_allocations"
    __table_args__ = (
        UniqueConstraint("allocation_round_id", "commitment_id", name="uq_collective_round_commitment_allocation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    allocation_round_id: Mapped[int] = mapped_column(ForeignKey("collective_allocation_rounds.id", ondelete="CASCADE"), index=True)
    commitment_id: Mapped[int] = mapped_column(ForeignKey("collective_conditional_commitments.id", ondelete="CASCADE"), index=True)
    allocation_entry_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    priority_hash: Mapped[str] = mapped_column(String(80), index=True)
    requested_quantity: Mapped[int] = mapped_column(Integer)
    allocated_quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="allocated", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
