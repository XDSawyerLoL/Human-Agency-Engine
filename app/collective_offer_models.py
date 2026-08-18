from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CollectiveMarketWindow(Base):
    __tablename__ = "collective_market_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_id: Mapped[int] = mapped_column(ForeignKey("collective_intent_cohorts.id"), index=True)
    window_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_hash: Mapped[str] = mapped_column(String(80), index=True)
    challenge_nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    public_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CollectiveMarketOffer(Base):
    __tablename__ = "collective_market_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    window_id: Mapped[int] = mapped_column(ForeignKey("collective_market_windows.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    responder_id: Mapped[str] = mapped_column(String(80), index=True)
    responder_label: Mapped[str] = mapped_column(String(255), default="")
    public_key_b64: Mapped[str] = mapped_column(String(128))
    signature_b64: Mapped[str] = mapped_column(Text)
    offer_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    group_eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="signed", index=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CollectiveOfferEvaluation(Base):
    __tablename__ = "collective_offer_evaluations"
    __table_args__ = (
        UniqueConstraint("membership_id", "offer_db_id", name="uq_collective_membership_offer_evaluation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("collective_intent_memberships.id", ondelete="CASCADE"), index=True)
    offer_db_id: Mapped[int] = mapped_column(ForeignKey("collective_market_offers.id", ondelete="CASCADE"), index=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    envelope_hash: Mapped[str] = mapped_column(String(80), index=True)
    provisional_eligible: Mapped[bool] = mapped_column(default=False, index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    score_components: Mapped[dict] = mapped_column(JSON, default=dict)
    fiduciary_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    commission_excluded: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
