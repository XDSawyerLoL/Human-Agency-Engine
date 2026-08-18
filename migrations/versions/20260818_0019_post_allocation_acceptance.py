"""add explicit post-allocation acceptance decisions

Revision ID: 20260818_0019
Revises: 20260818_0018
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0019"
down_revision = "20260818_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_allocation_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("private_allocation_id", sa.Integer(), nullable=False),
        sa.Column("commitment_id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("allocation_set_hash", sa.String(length=80), nullable=False),
        sa.Column("offer_hash", sa.String(length=80), nullable=False),
        sa.Column("conditions_hash", sa.String(length=80), nullable=False),
        sa.Column("envelope_hash", sa.String(length=80), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("exact_total_amount", sa.Float(), nullable=False),
        sa.Column("decision_hash", sa.String(length=80), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["private_allocation_id"], ["collective_private_allocations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["commitment_id"], ["collective_conditional_commitments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("private_allocation_id", name="uq_collective_private_allocation_decision"),
        sa.UniqueConstraint("decision_id"),
        sa.UniqueConstraint("decision_hash"),
    )
    for column in (
        "user_id", "private_allocation_id", "commitment_id", "decision_id", "decision",
        "allocation_set_hash", "offer_hash", "conditions_hash", "envelope_hash", "decision_hash",
        "decided_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_collective_allocation_decisions_{column}"),
            "collective_allocation_decisions",
            [column],
            unique=(column in {"decision_id", "decision_hash"}),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "private_allocation_id", "commitment_id", "decision_id", "decision",
        "allocation_set_hash", "offer_hash", "conditions_hash", "envelope_hash", "decision_hash",
        "decided_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_collective_allocation_decisions_{column}"), table_name="collective_allocation_decisions")
    op.drop_table("collective_allocation_decisions")
