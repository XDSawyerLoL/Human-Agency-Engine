"""add HORIZON provisional forecasts and resolutions

Revision ID: 20260819_0030
Revises: 20260819_0029
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0030"
down_revision = "20260819_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_provisional_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forecast_key", sa.String(length=96), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("fact_status", sa.String(length=40), nullable=False),
        sa.Column("candidate_snapshot", sa.JSON(), nullable=False),
        sa.Column("pattern_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_classes", sa.JSON(), nullable=False),
        sa.Column("corroboration_score", sa.Float(), nullable=False),
        sa.Column("provisional_score", sa.Float(), nullable=False),
        sa.Column("hypothesis_band", sa.String(length=32), nullable=False),
        sa.Column("predicted_response", sa.Text(), nullable=False),
        sa.Column("probability_basis", sa.String(length=64), nullable=False),
        sa.Column("geography_status", sa.String(length=32), nullable=False),
        sa.Column("user_surface_allowed", sa.Boolean(), nullable=False),
        sa.Column("external_action_allowed", sa.Boolean(), nullable=False),
        sa.Column("interpretation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["horizon_event_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("forecast_key", name="uq_horizon_provisional_forecast_key"),
    )
    for column in (
        "forecast_key", "candidate_id", "pattern_id", "as_of", "fact_status",
        "hypothesis_band", "geography_status", "user_surface_allowed", "created_at",
    ):
        op.create_index(
            f"ix_horizon_provisional_forecasts_{column}",
            "horizon_provisional_forecasts",
            [column],
            unique=column == "forecast_key",
        )

    op.create_table(
        "horizon_provisional_resolutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=False),
        sa.Column("resolution_type", sa.String(length=32), nullable=False),
        sa.Column("promoted_event_id", sa.Integer(), nullable=True),
        sa.Column("corroborated_at", sa.DateTime(), nullable=True),
        sa.Column("corroboration_lead_time_hours", sa.Float(), nullable=True),
        sa.Column("predictive_lead_time_hours", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["forecast_id"], ["horizon_provisional_forecasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promoted_event_id"], ["horizon_global_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("forecast_id", name="uq_horizon_provisional_resolution_forecast"),
    )
    for column in ("forecast_id", "resolution_type", "promoted_event_id", "corroborated_at", "resolved_at"):
        op.create_index(
            f"ix_horizon_provisional_resolutions_{column}",
            "horizon_provisional_resolutions",
            [column],
            unique=column == "forecast_id",
        )


def downgrade() -> None:
    op.drop_table("horizon_provisional_resolutions")
    op.drop_table("horizon_provisional_forecasts")
