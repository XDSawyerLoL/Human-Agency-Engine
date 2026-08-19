"""add HORIZON event graph snapshots

Revision ID: 20260820_0037
Revises: 20260820_0036
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0037"
down_revision = "20260820_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_event_graph_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("graph_key", sa.String(length=96), nullable=False),
        sa.Column("engine_version", sa.String(length=96), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("window_start_at", sa.DateTime(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("episode_count", sa.Integer(), nullable=False),
        sa.Column("graph_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_key", name="uq_horizon_event_graph_snapshot_key"),
    )
    for column in (
        "graph_key", "engine_version", "as_of", "window_start_at", "created_at",
    ):
        op.create_index(
            f"ix_horizon_event_graph_snapshots_{column}",
            "horizon_event_graph_snapshots",
            [column],
            unique=column == "graph_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_event_graph_snapshots")
