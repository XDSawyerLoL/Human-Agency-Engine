from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class UserVaultClaim(Base):
    __tablename__ = "user_vault_claims"
    __table_args__ = (
        UniqueConstraint("user_id", "claim_type", name="uq_user_vault_claim_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    claim_type: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    value_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SelectiveDisclosureGrant(Base):
    __tablename__ = "selective_disclosure_grants"
    __table_args__ = (
        UniqueConstraint("settlement_permit_id", name="uq_disclosure_parent_settlement_permit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    settlement_permit_id: Mapped[int] = mapped_column(
        ForeignKey("pseudonymous_settlement_permits.id", ondelete="CASCADE"), index=True
    )
    signing_identity_id: Mapped[int] = mapped_column(
        ForeignKey("agent_signing_identities.id", ondelete="CASCADE"), index=True
    )
    grant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    audience: Mapped[str] = mapped_column(String(96), index=True)
    claim_types: Mapped[list] = mapped_column(JSON, default=list)
    claim_set_hash: Mapped[str] = mapped_column(String(80), index=True)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class SelectiveDisclosureUse(Base):
    __tablename__ = "selective_disclosure_uses"
    __table_args__ = (
        UniqueConstraint("grant_db_id", "request_id", name="uq_disclosure_grant_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_db_id: Mapped[int] = mapped_column(
        ForeignKey("selective_disclosure_grants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    audience: Mapped[str] = mapped_column(String(96), index=True)
    disclosed_claim_types: Mapped[list] = mapped_column(JSON, default=list)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
