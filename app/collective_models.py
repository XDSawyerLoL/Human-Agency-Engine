from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveIntentCohort(Base):
    __tablename__ = "collective_intent_cohorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    request_type: Mapped[str] = mapped_column(String(24), index=True)
    category: Mapped[str] = mapped_column(String(96), index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    minimum_cohort_size: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CollectiveIntentMembership(Base):
    __tablename__ = "collective_intent_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "cohort_id", name="uq_collective_user_cohort"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    envelope_db_id: Mapped[int] = mapped_column(ForeignKey("private_intent_envelopes.id", ondelete="CASCADE"), index=True)
    cohort_id: Mapped[int] = mapped_column(ForeignKey("collective_intent_cohorts.id"), index=True)
    membership_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contribution_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
