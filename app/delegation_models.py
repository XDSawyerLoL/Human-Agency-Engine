from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class AgentSigningIdentity(Base):
    __tablename__ = "agent_signing_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(16), default="Ed25519")
    public_key_b64: Mapped[str] = mapped_column(String(128))
    encrypted_private_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class DelegationGrant(Base):
    __tablename__ = "delegation_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey("agent_signing_identities.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_interventions.id", ondelete="CASCADE"), index=True)
    grant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), index=True)
    audience: Mapped[str] = mapped_column(String(255), index=True)
    capability: Mapped[str] = mapped_column(String(32), index=True)
    mandate_version: Mapped[int] = mapped_column(Integer, index=True)
    action_type: Mapped[str] = mapped_column(String(96), default="")
    action_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revocation_reason: Mapped[str] = mapped_column(Text, default="")


class DelegationUse(Base):
    __tablename__ = "delegation_uses"
    __table_args__ = (
        UniqueConstraint("grant_id", "request_id", name="uq_delegation_use_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("delegation_grants.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    audience: Mapped[str] = mapped_column(String(255))
    action_fingerprint: Mapped[str] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
