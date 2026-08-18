"""add amount-only non-debit payment intent capabilities

Revision ID: 20260818_0023
Revises: 20260818_0022
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0023"
down_revision = "20260818_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_intent_capabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("settlement_permit_id", sa.Integer(), nullable=False),
        sa.Column("signing_identity_id", sa.Integer(), nullable=False),
        sa.Column("capability_id", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=80), nullable=False),
        sa.Column("payment_terms_hash", sa.String(length=80), nullable=False),
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
            ["settlement_permit_id"],
            ["pseudonymous_settlement_permits.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signing_identity_id"],
            ["agent_signing_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settlement_permit_id", name="uq_payment_intent_parent_settlement_permit"),
        sa.UniqueConstraint("capability_id"),
        sa.UniqueConstraint("subject_ref"),
        sa.UniqueConstraint("token_hash"),
        sa.UniqueConstraint("payment_terms_hash"),
    )
    for column in (
        "user_id", "settlement_permit_id", "signing_identity_id", "capability_id", "subject_ref",
        "audience", "token_hash", "payment_terms_hash", "readiness_hash", "allocation_set_hash",
        "accepted_set_hash", "offer_hash", "decision_hash", "conditions_hash", "mandate_version",
        "status", "issued_at", "expires_at", "consumed_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_payment_intent_capabilities_{column}"),
            "payment_intent_capabilities",
            [column],
            unique=(column in {"capability_id", "subject_ref", "token_hash", "payment_terms_hash"}),
        )

    op.create_table(
        "payment_intent_capability_uses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capability_db_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["capability_db_id"],
            ["payment_intent_capabilities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability_db_id", "request_id", name="uq_payment_intent_capability_request"),
    )
    for column in ("capability_db_id", "request_id", "audience", "recorded_at"):
        op.create_index(
            op.f(f"ix_payment_intent_capability_uses_{column}"),
            "payment_intent_capability_uses",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in reversed(("capability_db_id", "request_id", "audience", "recorded_at")):
        op.drop_index(
            op.f(f"ix_payment_intent_capability_uses_{column}"),
            table_name="payment_intent_capability_uses",
        )
    op.drop_table("payment_intent_capability_uses")

    for column in reversed((
        "user_id", "settlement_permit_id", "signing_identity_id", "capability_id", "subject_ref",
        "audience", "token_hash", "payment_terms_hash", "readiness_hash", "allocation_set_hash",
        "accepted_set_hash", "offer_hash", "decision_hash", "conditions_hash", "mandate_version",
        "status", "issued_at", "expires_at", "consumed_at", "revoked_at",
    )):
        op.drop_index(
            op.f(f"ix_payment_intent_capabilities_{column}"),
            table_name="payment_intent_capabilities",
        )
    op.drop_table("payment_intent_capabilities")
