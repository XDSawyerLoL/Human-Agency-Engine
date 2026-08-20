"""add HORIZON permanent collector state

Revision ID: 20260820_0038
Revises: 20260820_0037
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0038"
down_revision = "20260820_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_collector_leases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_key", sa.String(length=96), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collector_key", name="uq_horizon_collector_lease_key"),
    )
    for column in ("collector_key", "owner_id", "acquired_at", "heartbeat_at", "lease_expires_at", "updated_at"):
        op.create_index(
            f"ix_horizon_collector_leases_{column}",
            "horizon_collector_leases",
            [column],
            unique=column == "collector_key",
        )

    op.create_table(
        "horizon_collector_source_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=96), nullable=False),
        sa.Column("cadence_seconds", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("last_result", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_horizon_collector_source_state_key"),
    )
    for column in ("source_key", "next_due_at", "last_attempt_at", "last_success_at", "updated_at"):
        op.create_index(
            f"ix_horizon_collector_source_states_{column}",
            "horizon_collector_source_states",
            [column],
            unique=column == "source_key",
        )

    op.create_table(
        "horizon_collector_cycles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cycle_key", sa.String(length=96), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("due_sources", sa.JSON(), nullable=False),
        sa.Column("source_results", sa.JSON(), nullable=False),
        sa.Column("postprocessing", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_key", name="uq_horizon_collector_cycle_key"),
    )
    for column in ("cycle_key", "owner_id", "trigger", "started_at", "finished_at", "status", "created_at"):
        op.create_index(
            f"ix_horizon_collector_cycles_{column}",
            "horizon_collector_cycles",
            [column],
            unique=column == "cycle_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_collector_cycles")
    op.drop_table("horizon_collector_source_states")
    op.drop_table("horizon_collector_leases")
