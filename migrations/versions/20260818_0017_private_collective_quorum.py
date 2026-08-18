"""add private conditional collective commitments

Revision ID: 20260818_0017
Revises: 20260818_0016
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0017"
down_revision = "20260818_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_conditional_commitments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("offer_db_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("commitment_id", sa.String(length=64), nullable=False),
        sa.Column("offer_hash", sa.String(length=80), nullable=False),
        sa.Column("source_set_hash", sa.String(length=80), nullable=False),
        sa.Column("aggregate_hash", sa.String(length=80), nullable=False),
        sa.Column("envelope_hash", sa.String(length=80), nullable=False),
        sa.Column("conditions_hash", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["collective_intent_memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_db_id"], ["collective_market_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_id"], ["collective_offer_evaluations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "offer_db_id", name="uq_collective_user_offer_commitment"),
        sa.UniqueConstraint("commitment_id"),
    )
    for column in (
        "user_id", "membership_id", "offer_db_id", "evaluation_id", "commitment_id", "offer_hash",
        "source_set_hash", "aggregate_hash", "envelope_hash", "conditions_hash", "status",
        "created_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_collective_conditional_commitments_{column}"),
            "collective_conditional_commitments",
            [column],
            unique=(column == "commitment_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "membership_id", "offer_db_id", "evaluation_id", "commitment_id", "offer_hash",
        "source_set_hash", "aggregate_hash", "envelope_hash", "conditions_hash", "status",
        "created_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_collective_conditional_commitments_{column}"), table_name="collective_conditional_commitments")
    op.drop_table("collective_conditional_commitments")
