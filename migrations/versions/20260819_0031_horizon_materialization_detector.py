"""add HORIZON automatic materialization detection ledger

Revision ID: 20260819_0031
Revises: 20260819_0030
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0031"
down_revision = "20260819_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_materialization_detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("detection_key", sa.String(length=96), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("became_obvious_at", sa.DateTime(), nullable=False),
        sa.Column("predictive_lead_time_hours", sa.Float(), nullable=False),
        sa.Column("evidence_signal_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_sources", sa.JSON(), nullable=False),
        sa.Column("materialization_signal_types", sa.JSON(), nullable=False),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["forecast_id"], ["horizon_forecasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("detection_key", name="uq_horizon_materialization_detection_key"),
        sa.UniqueConstraint("forecast_id", name="uq_horizon_materialization_forecast"),
    )
    for column in (
        "detection_key", "forecast_id", "event_id", "pattern_id", "became_obvious_at", "created_at"
    ):
        op.create_index(
            f"ix_horizon_materialization_detections_{column}",
            "horizon_materialization_detections",
            [column],
            unique=column in {"detection_key", "forecast_id"},
        )


def downgrade() -> None:
    op.drop_table("horizon_materialization_detections")
