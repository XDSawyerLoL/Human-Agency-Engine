"""add HORIZON forecast expiry ledger

Revision ID: 20260819_0032
Revises: 20260819_0031
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0032"
down_revision = "20260819_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_forecast_expiries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expiry_key", sa.String(length=96), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("expected_onset_high", sa.DateTime(), nullable=False),
        sa.Column("grace_hours", sa.Float(), nullable=False),
        sa.Column("expiry_deadline", sa.DateTime(), nullable=False),
        sa.Column("expired_at", sa.DateTime(), nullable=False),
        sa.Column("checked_materialization_signal_types", sa.JSON(), nullable=False),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["forecast_id"], ["horizon_forecasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expiry_key", name="uq_horizon_forecast_expiry_key"),
        sa.UniqueConstraint("forecast_id", name="uq_horizon_forecast_expiry_forecast"),
    )
    for column in (
        "expiry_key", "forecast_id", "event_id", "pattern_id",
        "expected_onset_high", "expiry_deadline", "expired_at", "created_at",
    ):
        op.create_index(
            f"ix_horizon_forecast_expiries_{column}",
            "horizon_forecast_expiries",
            [column],
            unique=column in {"expiry_key", "forecast_id"},
        )


def downgrade() -> None:
    op.drop_table("horizon_forecast_expiries")
