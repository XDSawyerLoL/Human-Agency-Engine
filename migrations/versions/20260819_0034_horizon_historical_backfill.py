"""add HORIZON historical backfill and coverage ledgers

Revision ID: 20260819_0034
Revises: 20260819_0033
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0034"
down_revision = "20260819_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_historical_coverage_intervals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_key", sa.String(length=96), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("coverage_kind", sa.String(length=32), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("signal_types", sa.JSON(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("completeness", sa.String(length=24), nullable=False),
        sa.Column("basis", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["horizon_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coverage_key", name="uq_horizon_historical_coverage_key"),
    )
    for column in ("coverage_key", "source_id", "coverage_kind", "start_at", "end_at", "completeness", "basis", "created_at"):
        op.create_index(
            f"ix_horizon_historical_coverage_intervals_{column}",
            "horizon_historical_coverage_intervals",
            [column],
            unique=column == "coverage_key",
        )

    op.create_table(
        "horizon_historical_backfill_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=96), nullable=False),
        sa.Column("engine_version", sa.String(length=96), nullable=False),
        sa.Column("adapter_kind", sa.String(length=96), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("requested_start_at", sa.DateTime(), nullable=False),
        sa.Column("requested_end_at", sa.DateTime(), nullable=False),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["horizon_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_horizon_historical_backfill_run_key"),
    )
    for column in (
        "run_key", "engine_version", "adapter_kind", "source_id", "requested_start_at",
        "requested_end_at", "status", "created_at",
    ):
        op.create_index(
            f"ix_horizon_historical_backfill_runs_{column}",
            "horizon_historical_backfill_runs",
            [column],
            unique=column == "run_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_historical_backfill_runs")
    op.drop_table("horizon_historical_coverage_intervals")
