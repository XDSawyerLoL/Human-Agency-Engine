"""add privacy-thresholded collective settlement readiness receipts

Revision ID: 20260818_0020
Revises: 20260818_0019
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0020"
down_revision = "20260818_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_settlement_readiness_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offer_db_id", sa.Integer(), nullable=False),
        sa.Column("allocation_round_id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("allocation_set_hash", sa.String(length=80), nullable=False),
        sa.Column("commitment_set_hash", sa.String(length=80), nullable=False),
        sa.Column("accepted_set_hash", sa.String(length=80), nullable=False),
        sa.Column("accepted_user_count", sa.Integer(), nullable=False),
        sa.Column("accepted_quantity", sa.Integer(), nullable=False),
        sa.Column("allocated_user_count", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("exact_total_amount", sa.Float(), nullable=False),
        sa.Column("minimum_anonymity_set", sa.Integer(), nullable=False),
        sa.Column("all_allocated_users_accepted", sa.Boolean(), nullable=False),
        sa.Column("commercial_minimum_met", sa.Boolean(), nullable=False),
        sa.Column("capacity_ok", sa.Boolean(), nullable=False),
        sa.Column("settlement_ready", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("external_dispatch_enabled", sa.Boolean(), nullable=False),
        sa.Column("payment_created", sa.Boolean(), nullable=False),
        sa.Column("order_created", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["offer_db_id"], ["collective_market_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["allocation_round_id"], ["collective_allocation_rounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "allocation_round_id",
            "accepted_set_hash",
            name="uq_collective_settlement_allocation_acceptance_set",
        ),
        sa.UniqueConstraint("receipt_id"),
    )
    for column in (
        "offer_db_id", "allocation_round_id", "receipt_id", "allocation_set_hash",
        "commitment_set_hash", "accepted_set_hash", "settlement_ready", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_settlement_readiness_receipts_{column}"),
            "collective_settlement_readiness_receipts",
            [column],
            unique=(column == "receipt_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "offer_db_id", "allocation_round_id", "receipt_id", "allocation_set_hash",
        "commitment_set_hash", "accepted_set_hash", "settlement_ready", "created_at",
    )):
        op.drop_index(
            op.f(f"ix_collective_settlement_readiness_receipts_{column}"),
            table_name="collective_settlement_readiness_receipts",
        )
    op.drop_table("collective_settlement_readiness_receipts")
