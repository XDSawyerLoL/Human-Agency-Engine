"""add HORIZON historical backtest run ledger

Revision ID: 20260819_0033
Revises: 20260819_0032
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0033"
down_revision = "20260819_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_historical_backtest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=96), nullable=False),
        sa.Column("requested_start_at", sa.DateTime(), nullable=False),
        sa.Column("requested_end_at", sa.DateTime(), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("max_events", sa.Integer(), nullable=False),
        sa.Column("max_cases", sa.Integer(), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=96), nullable=False),
        sa.Column("selected_event_ids", sa.JSON(), nullable=False),
        sa.Column("selected_forecast_ids", sa.JSON(), nullable=False),
        sa.Column("excluded_collateral_forecast_ids", sa.JSON(), nullable=False),
        sa.Column("case_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_horizon_historical_backtest_run_key"),
    )
    for column in (
        "run_key",
        "user_id",
        "engine_version",
        "requested_start_at",
        "requested_end_at",
        "evaluation_as_of",
        "dataset_fingerprint",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_horizon_historical_backtest_runs_{column}",
            "horizon_historical_backtest_runs",
            [column],
            unique=column == "run_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_historical_backtest_runs")
