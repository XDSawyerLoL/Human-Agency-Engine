"""add proof of mandate delegation

Revision ID: 20260818_0008
Revises: 20260818_0007
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0008"
down_revision = "20260818_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_signing_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=16), nullable=False),
        sa.Column("public_key_b64", sa.String(length=128), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id"),
    )
    for column in ("user_id", "key_id", "revoked_at"):
        op.create_index(op.f(f"ix_agent_signing_identities_{column}"), "agent_signing_identities", [column], unique=(column == "key_id"))

    op.create_table(
        "delegation_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=96), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["identity_id"], ["agent_signing_identities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_id"),
        sa.UniqueConstraint("nonce"),
    )
    for column in (
        "user_id", "identity_id", "candidate_id", "grant_id", "subject_ref", "audience",
        "capability", "mandate_version", "action_fingerprint", "nonce", "issued_at", "expires_at", "revoked_at",
    ):
        op.create_index(op.f(f"ix_delegation_grants_{column}"), "delegation_grants", [column], unique=(column in {"grant_id", "nonce"}))

    op.create_table(
        "delegation_uses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["grant_id"], ["delegation_grants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_id", "request_id", name="uq_delegation_use_request"),
    )
    for column in ("grant_id", "request_id", "recorded_at"):
        op.create_index(op.f(f"ix_delegation_uses_{column}"), "delegation_uses", [column], unique=False)


def downgrade() -> None:
    for column in reversed(("grant_id", "request_id", "recorded_at")):
        op.drop_index(op.f(f"ix_delegation_uses_{column}"), table_name="delegation_uses")
    op.drop_table("delegation_uses")
    for column in reversed((
        "user_id", "identity_id", "candidate_id", "grant_id", "subject_ref", "audience",
        "capability", "mandate_version", "action_fingerprint", "nonce", "issued_at", "expires_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_delegation_grants_{column}"), table_name="delegation_grants")
    op.drop_table("delegation_grants")
    for column in reversed(("user_id", "key_id", "revoked_at")):
        op.drop_index(op.f(f"ix_agent_signing_identities_{column}"), table_name="agent_signing_identities")
    op.drop_table("agent_signing_identities")
