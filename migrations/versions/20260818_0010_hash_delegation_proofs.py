"""replace plaintext delegation proofs with one-way hashes

Revision ID: 20260818_0010
Revises: 20260818_0009
Create Date: 2026-08-18

This migration is intentionally irreversible: plaintext bearer proofs are
hashed and then destroyed. A downgrade cannot reconstruct those credentials.
"""

import hashlib

from alembic import op
import sqlalchemy as sa

revision = "20260818_0010"
down_revision = "20260818_0009"
branch_labels = None
depends_on = None


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table("delegation_grants") as batch:
        batch.add_column(sa.Column("token_hash", sa.String(length=80), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, token FROM delegation_grants")).mappings().all()
    for row in rows:
        bind.execute(
            sa.text("UPDATE delegation_grants SET token_hash = :token_hash WHERE id = :id"),
            {"token_hash": _hash_token(row["token"]), "id": row["id"]},
        )

    with op.batch_alter_table("delegation_grants") as batch:
        batch.alter_column(
            "token_hash",
            existing_type=sa.String(length=80),
            nullable=False,
        )
        batch.drop_column("token")

    op.create_index(
        op.f("ix_delegation_grants_token_hash"),
        "delegation_grants",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError(
        "irreversible security migration: plaintext delegation proofs were intentionally destroyed"
    )
