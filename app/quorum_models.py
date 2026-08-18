from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveConditionalCommitment(Base):
    __tablename__ = "collective_conditional_commitments"
    __table_args__ = (
        UniqueConstraint("user_id", "offer_db_id", name="uq_collective_user_offer_commitment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("collective_intent_memberships.id", ondelete="CASCADE"), index=True)
    offer_db_id: Mapped[int] = mapped_column(ForeignKey("collective_market_offers.id", ondelete="CASCADE"), index=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("collective_offer_evaluations.id", ondelete="CASCADE"), index=True)
    commitment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    offer_hash: Mapped[str] = mapped_column(String(80), index=True)
    source_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_hash: Mapped[str] = mapped_column(String(80), index=True)
    envelope_hash: Mapped[str] = mapped_column(String(80), index=True)
    conditions_hash: Mapped[str] = mapped_column(String(80), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
