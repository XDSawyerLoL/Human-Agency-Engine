from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PrivateIntentEnvelope(Base):
    __tablename__ = "private_intent_envelopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    envelope_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_type: Mapped[str] = mapped_column(String(24), index=True)
    category: Mapped[str] = mapped_column(String(96), index=True)
    disclosure: Mapped[dict] = mapped_column(JSON, default=dict)
    ranking_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    candidate_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    challenge_nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    envelope_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class MarketOffer(Base):
    __tablename__ = "market_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    envelope_db_id: Mapped[int] = mapped_column(ForeignKey("private_intent_envelopes.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    responder_id: Mapped[str] = mapped_column(String(80), index=True)
    responder_label: Mapped[str] = mapped_column(String(255), default="")
    public_key_b64: Mapped[str] = mapped_column(String(128))
    signature_b64: Mapped[str] = mapped_column(Text)
    offer_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="signed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
