"""add snapshot-bound collective market offers and private evaluations

Revision ID: 20260818_0016
Revises: 20260818_0015
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0016"
down_revision = "20260818_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_market_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cohort_id", sa.Integer(), nullable=False),
        sa.Column("window_id", sa.String(length=64), nullable=False),
        sa.Column("source_set_hash", sa.String(length=80), nullable=False),
        sa.Column("aggregate_hash", sa.String(length=80), nullable=False),
        sa.Column("challenge_nonce", sa.String(length=64), nullable=False),
        sa.Column("public_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cohort_id"], ["collective_intent_cohorts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_id"),
        sa.UniqueConstraint("challenge_nonce"),
    )
    for column in (
        "cohort_id", "window_id", "source_set_hash", "aggregate_hash", "challenge_nonce",
        "status", "expires_at", "created_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_collective_market_windows_{column}"),
            "collective_market_windows",
            [column],
            unique=(column in {"window_id", "challenge_nonce"}),
        )

    op.create_table(
        "collective_market_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("window_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.String(length=96), nullable=False),
        sa.Column("responder_id", sa.String(length=80), nullable=False),
        sa.Column("responder_label", sa.String(length=255), nullable=False),
        sa.Column("public_key_b64", sa.String(length=128), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("offer_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("group_eligibility", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["window_id"], ["collective_market_windows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id"),
        sa.UniqueConstraint("offer_hash"),
    )
    for column in (
        "window_id", "offer_id", "responder_id", "offer_hash", "status", "valid_until", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_market_offers_{column}"),
            "collective_market_offers",
            [column],
            unique=(column in {"offer_id", "offer_hash"}),
        )

    op.create_table(
        "collective_offer_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("offer_db_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.String(length=64), nullable=False),
        sa.Column("envelope_hash", sa.String(length=80), nullable=False),
        sa.Column("provisional_eligible", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("score_components", sa.JSON(), nullable=False),
        sa.Column("fiduciary_score", sa.Float(), nullable=True),
        sa.Column("commission_excluded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["collective_intent_memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_db_id"], ["collective_market_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_id", "offer_db_id", name="uq_collective_membership_offer_evaluation"),
        sa.UniqueConstraint("evaluation_id"),
    )
    for column in (
        "user_id", "membership_id", "offer_db_id", "evaluation_id", "envelope_hash",
        "provisional_eligible", "fiduciary_score", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_offer_evaluations_{column}"),
            "collective_offer_evaluations",
            [column],
            unique=(column == "evaluation_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "membership_id", "offer_db_id", "evaluation_id", "envelope_hash",
        "provisional_eligible", "fiduciary_score", "created_at",
    )):
        op.drop_index(op.f(f"ix_collective_offer_evaluations_{column}"), table_name="collective_offer_evaluations")
    op.drop_table("collective_offer_evaluations")

    for column in reversed((
        "window_id", "offer_id", "responder_id", "offer_hash", "status", "valid_until", "created_at",
    )):
        op.drop_index(op.f(f"ix_collective_market_offers_{column}"), table_name="collective_market_offers")
    op.drop_table("collective_market_offers")

    for column in reversed((
        "cohort_id", "window_id", "source_set_hash", "aggregate_hash", "challenge_nonce",
        "status", "expires_at", "created_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_collective_market_windows_{column}"), table_name="collective_market_windows")
    op.drop_table("collective_market_windows")
