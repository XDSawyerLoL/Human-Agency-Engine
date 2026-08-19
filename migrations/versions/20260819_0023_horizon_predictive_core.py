"""add HORIZON predictive core

Revision ID: 20260819_0023
Revises: 20260818_0022
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0023"
down_revision = "20260818_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_global_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=96), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_reliability", sa.Float(), nullable=False),
        sa.Column("raw_facts", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    for column in ("event_key", "event_type", "source", "occurred_at", "first_observed_at", "status", "created_at"):
        op.create_index(op.f(f"ix_horizon_global_events_{column}"), "horizon_global_events", [column], unique=(column == "event_key"))

    op.create_table(
        "horizon_social_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("signal_key", sa.String(length=192), nullable=False),
        sa.Column("signal_type", sa.String(length=96), nullable=False),
        sa.Column("source", sa.String(length=96), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("baseline", sa.Float(), nullable=True),
        sa.Column("normalized_score", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=24), nullable=False),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_key"),
    )
    for column in ("event_id", "signal_key", "signal_type", "source", "direction", "observed_at"):
        op.create_index(op.f(f"ix_horizon_social_signals_{column}"), "horizon_social_signals", [column], unique=(column == "signal_key"))

    op.create_table(
        "horizon_behavior_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("required_signal_types", sa.JSON(), nullable=False),
        sa.Column("predicted_response", sa.Text(), nullable=False),
        sa.Column("mechanism_chain", sa.JSON(), nullable=False),
        sa.Column("expected_lag_hours_low", sa.Integer(), nullable=False),
        sa.Column("expected_lag_hours_high", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("knowledge_available_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern_key"),
    )
    for column in ("pattern_key", "knowledge_available_at", "status"):
        op.create_index(op.f(f"ix_horizon_behavior_patterns_{column}"), "horizon_behavior_patterns", [column], unique=(column == "pattern_key"))

    op.create_table(
        "horizon_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forecast_key", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("event_facts_snapshot", sa.JSON(), nullable=False),
        sa.Column("social_signal_snapshot", sa.JSON(), nullable=False),
        sa.Column("personal_exposure", sa.JSON(), nullable=False),
        sa.Column("behavior_chain", sa.JSON(), nullable=False),
        sa.Column("predicted_outcome", sa.Text(), nullable=False),
        sa.Column("likelihood_band", sa.String(length=24), nullable=False),
        sa.Column("predictive_score", sa.Float(), nullable=False),
        sa.Column("probability_low", sa.Float(), nullable=True),
        sa.Column("probability_mid", sa.Float(), nullable=True),
        sa.Column("probability_high", sa.Float(), nullable=True),
        sa.Column("probability_basis", sa.String(length=64), nullable=False),
        sa.Column("expected_onset_low", sa.DateTime(), nullable=True),
        sa.Column("expected_onset_high", sa.DateTime(), nullable=True),
        sa.Column("decision_window", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("calibration_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("forecast_key", name="uq_horizon_forecast_key"),
    )
    for column in ("forecast_key", "user_id", "event_id", "pattern_id", "mode", "as_of", "likelihood_band", "calibration_status", "status", "created_at"):
        op.create_index(op.f(f"ix_horizon_forecasts_{column}"), "horizon_forecasts", [column], unique=(column == "forecast_key"))

    op.create_table(
        "horizon_forecast_resolutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=False),
        sa.Column("outcome_occurred", sa.Boolean(), nullable=True),
        sa.Column("outcome_summary", sa.Text(), nullable=False),
        sa.Column("correctness", sa.String(length=24), nullable=False),
        sa.Column("became_obvious_at", sa.DateTime(), nullable=True),
        sa.Column("personal_action_at", sa.DateTime(), nullable=True),
        sa.Column("predictive_lead_time_hours", sa.Float(), nullable=True),
        sa.Column("actionable_lead_time_hours", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["forecast_id"], ["horizon_forecasts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("forecast_id", name="uq_horizon_resolution_forecast"),
    )
    for column in ("forecast_id", "correctness", "became_obvious_at", "resolved_at"):
        op.create_index(op.f(f"ix_horizon_forecast_resolutions_{column}"), "horizon_forecast_resolutions", [column], unique=(column == "forecast_id"))


def downgrade() -> None:
    op.drop_table("horizon_forecast_resolutions")
    op.drop_table("horizon_forecasts")
    op.drop_table("horizon_behavior_patterns")
    op.drop_table("horizon_social_signals")
    op.drop_table("horizon_global_events")
