"""add HORIZON convergence snapshot ledger

Revision ID: 20260820_0036
Revises: 20260820_0035
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0036"
down_revision = "20260820_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_convergence_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_key", sa.String(length=96), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=96), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("independent_sources", sa.Integer(), nullable=False),
        sa.Column("source_classes", sa.JSON(), nullable=False),
        sa.Column("evidence_roles", sa.JSON(), nullable=False),
        sa.Column("convergence_score", sa.Float(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_key", name="uq_horizon_convergence_snapshot_key"),
    )
    for column in (
        "snapshot_key", "event_id", "engine_version", "as_of", "convergence_score", "created_at",
    ):
        op.create_index(
            f"ix_horizon_convergence_snapshots_{column}",
            "horizon_convergence_snapshots",
            [column],
            unique=column == "snapshot_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_convergence_snapshots")
