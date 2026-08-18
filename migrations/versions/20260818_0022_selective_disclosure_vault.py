"""add encrypted user fulfillment claims and selective disclosure grants

Revision ID: 20260818_0022
Revises: 20260818_0021
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0022"
down_revision = "20260818_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_vault_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("value_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "claim_type", name="uq_user_vault_claim_type"),
    )
    for column in (
        "user_id", "claim_type", "value_fingerprint", "status", "created_at", "updated_at",
    ):
        op.create_index(
            op.f(f"ix_user_vault_claims_{column}"),
            "user_vault_claims",
            [column],
            unique=False,
        )

    op.create_table(
        "selective_disclosure_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("settlement_permit_id", sa.Integer(), nullable=False),
        sa.Column("signing_identity_id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=96), nullable=False),
        sa.Column("claim_types", sa.JSON(), nullable=False),
        sa.Column("claim_set_hash", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["settlement_permit_id"], ["pseudonymous_settlement_permits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["signing_identity_id"], ["agent_signing_identities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settlement_permit_id", name="uq_disclosure_parent_settlement_permit"),
        sa.UniqueConstraint("grant_id"),
        sa.UniqueConstraint("subject_ref"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in (
        "user_id", "settlement_permit_id", "signing_identity_id", "grant_id", "subject_ref",
        "audience", "claim_set_hash", "token_hash", "status", "issued_at", "expires_at",
        "consumed_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_selective_disclosure_grants_{column}"),
            "selective_disclosure_grants",
            [column],
            unique=(column in {"grant_id", "subject_ref", "token_hash"}),
        )

    op.create_table(
        "selective_disclosure_uses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grant_db_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=96), nullable=False),
        sa.Column("disclosed_claim_types", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["grant_db_id"], ["selective_disclosure_grants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_db_id", "request_id", name="uq_disclosure_grant_request"),
    )
    for column in ("grant_db_id", "request_id", "audience", "recorded_at"):
        op.create_index(
            op.f(f"ix_selective_disclosure_uses_{column}"),
            "selective_disclosure_uses",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in reversed(("grant_db_id", "request_id", "audience", "recorded_at")):
        op.drop_index(op.f(f"ix_selective_disclosure_uses_{column}"), table_name="selective_disclosure_uses")
    op.drop_table("selective_disclosure_uses")

    for column in reversed((
        "user_id", "settlement_permit_id", "signing_identity_id", "grant_id", "subject_ref",
        "audience", "claim_set_hash", "token_hash", "status", "issued_at", "expires_at",
        "consumed_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_selective_disclosure_grants_{column}"), table_name="selective_disclosure_grants")
    op.drop_table("selective_disclosure_grants")

    for column in reversed((
        "user_id", "claim_type", "value_fingerprint", "status", "created_at", "updated_at",
    )):
        op.drop_index(op.f(f"ix_user_vault_claims_{column}"), table_name="user_vault_claims")
    op.drop_table("user_vault_claims")
