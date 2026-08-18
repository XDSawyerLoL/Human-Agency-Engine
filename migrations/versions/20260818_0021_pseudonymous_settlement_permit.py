"""add pseudonymous one-time settlement preparation permits

Revision ID: 20260818_0021
Revises: 20260818_0020
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0021"
down_revision = "20260818_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pseudonymous_settlement_permits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("settlement_receipt_id", sa.Integer(), nullable=False),
        sa.Column("private_allocation_id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("signing_identity_id", sa.Integer(), nullable=False),
        sa.Column("permit_id", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=96), nullable=False),
        sa.Column("token_hash", sa.String(length=80), nullable=False),
        sa.Column("readiness_hash", sa.String(length=80), nullable=False),
        sa.Column("allocation_set_hash", sa.String(length=80), nullable=False),
        sa.Column("accepted_set_hash", sa.String(length=80), nullable=False),
        sa.Column("offer_hash", sa.String(length=80), nullable=False),
        sa.Column("decision_hash", sa.String(length=80), nullable=False),
        sa.Column("conditions_hash", sa.String(length=80), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("exact_total_amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["settlement_receipt_id"],
            ["collective_settlement_readiness_receipts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["private_allocation_id"],
            ["collective_private_allocations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["collective_allocation_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signing_identity_id"],
            ["agent_signing_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", name="uq_settlement_permit_exact_acceptance"),
        sa.UniqueConstraint("permit_id"),
        sa.UniqueConstraint("subject_ref"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in (
        "user_id", "settlement_receipt_id", "private_allocation_id", "decision_id",
        "signing_identity_id", "permit_id", "subject_ref", "audience", "token_hash",
        "readiness_hash", "allocation_set_hash", "accepted_set_hash", "offer_hash",
        "decision_hash", "conditions_hash", "mandate_version", "status", "issued_at",
        "expires_at", "consumed_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_pseudonymous_settlement_permits_{column}"),
            "pseudonymous_settlement_permits",
            [column],
            unique=(column in {"permit_id", "subject_ref", "token_hash"}),
        )

    op.create_table(
        "settlement_permit_uses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("permit_db_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=96), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permit_db_id"],
            ["pseudonymous_settlement_permits.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("permit_db_id", "request_id", name="uq_settlement_permit_request"),
    )
    for column in ("permit_db_id", "request_id", "audience", "recorded_at"):
        op.create_index(
            op.f(f"ix_settlement_permit_uses_{column}"),
            "settlement_permit_uses",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in reversed(("permit_db_id", "request_id", "audience", "recorded_at")):
        op.drop_index(op.f(f"ix_settlement_permit_uses_{column}"), table_name="settlement_permit_uses")
    op.drop_table("settlement_permit_uses")

    for column in reversed((
        "user_id", "settlement_receipt_id", "private_allocation_id", "decision_id",
        "signing_identity_id", "permit_id", "subject_ref", "audience", "token_hash",
        "readiness_hash", "allocation_set_hash", "accepted_set_hash", "offer_hash",
        "decision_hash", "conditions_hash", "mandate_version", "status", "issued_at",
        "expires_at", "consumed_at", "revoked_at",
    )):
        op.drop_index(
            op.f(f"ix_pseudonymous_settlement_permits_{column}"),
            table_name="pseudonymous_settlement_permits",
        )
    op.drop_table("pseudonymous_settlement_permits")
