"""add deterministic privacy-preserving collective allocation

Revision ID: 20260818_0018
Revises: 20260818_0017
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0018"
down_revision = "20260818_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_allocation_rounds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offer_db_id", sa.Integer(), nullable=False),
        sa.Column("allocation_id", sa.String(length=64), nullable=False),
        sa.Column("commitment_set_hash", sa.String(length=80), nullable=False),
        sa.Column("seed_hash", sa.String(length=80), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("committed_user_count", sa.Integer(), nullable=False),
        sa.Column("committed_quantity", sa.Integer(), nullable=False),
        sa.Column("capacity_quantity", sa.Integer(), nullable=False),
        sa.Column("allocated_user_count", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("oversubscribed", sa.Boolean(), nullable=False),
        sa.Column("allocation_set_hash", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["offer_db_id"], ["collective_market_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_db_id", "commitment_set_hash", name="uq_collective_offer_commitment_set_allocation"),
        sa.UniqueConstraint("allocation_id"),
        sa.UniqueConstraint("allocation_set_hash"),
    )
    for column in (
        "offer_db_id", "allocation_id", "commitment_set_hash", "seed_hash", "algorithm_version",
        "allocation_set_hash", "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_allocation_rounds_{column}"),
            "collective_allocation_rounds",
            [column],
            unique=(column in {"allocation_id", "allocation_set_hash"}),
        )

    op.create_table(
        "collective_private_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("allocation_round_id", sa.Integer(), nullable=False),
        sa.Column("commitment_id", sa.Integer(), nullable=False),
        sa.Column("allocation_entry_id", sa.String(length=64), nullable=False),
        sa.Column("priority_hash", sa.String(length=80), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["allocation_round_id"], ["collective_allocation_rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["commitment_id"], ["collective_conditional_commitments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("allocation_round_id", "commitment_id", name="uq_collective_round_commitment_allocation"),
        sa.UniqueConstraint("allocation_entry_id"),
    )
    for column in (
        "user_id", "allocation_round_id", "commitment_id", "allocation_entry_id", "priority_hash",
        "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_private_allocations_{column}"),
            "collective_private_allocations",
            [column],
            unique=(column == "allocation_entry_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "allocation_round_id", "commitment_id", "allocation_entry_id", "priority_hash",
        "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_collective_private_allocations_{column}"), table_name="collective_private_allocations")
    op.drop_table("collective_private_allocations")

    for column in reversed((
        "offer_db_id", "allocation_id", "commitment_set_hash", "seed_hash", "algorithm_version",
        "allocation_set_hash", "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_collective_allocation_rounds_{column}"), table_name="collective_allocation_rounds")
    op.drop_table("collective_allocation_rounds")
