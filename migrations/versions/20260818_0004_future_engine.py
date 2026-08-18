"""add auditable future scenario engine

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0004"
down_revision = "20260818_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "future_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("state_snapshot", sa.JSON(), nullable=False),
        sa.Column("intent_snapshot", sa.JSON(), nullable=False),
        sa.Column("mandate_snapshot", sa.JSON(), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_future_runs_user_id"), "future_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_future_runs_created_at"), "future_runs", ["created_at"], unique=False)

    op.create_table(
        "future_scenarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scenario_type", sa.String(length=32), nullable=False),
        sa.Column("intervention", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("projected_metrics", sa.JSON(), nullable=False),
        sa.Column("uncertainty", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("agency_delta", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("claim_level", sa.String(length=32), nullable=False),
        sa.Column("robustness", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["future_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("run_id", "scenario_type", "claim_level", "robustness"):
        op.create_index(op.f(f"ix_future_scenarios_{column}"), "future_scenarios", [column], unique=False)

    op.create_table(
        "forecast_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("observed_metrics", sa.JSON(), nullable=False),
        sa.Column("observation_window", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["future_runs.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["future_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_forecast_outcomes_run_id"), "forecast_outcomes", ["run_id"], unique=False)
    op.create_index(op.f("ix_forecast_outcomes_scenario_id"), "forecast_outcomes", ["scenario_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_forecast_outcomes_scenario_id"), table_name="forecast_outcomes")
    op.drop_index(op.f("ix_forecast_outcomes_run_id"), table_name="forecast_outcomes")
    op.drop_table("forecast_outcomes")
    for column in reversed(("run_id", "scenario_type", "claim_level", "robustness")):
        op.drop_index(op.f(f"ix_future_scenarios_{column}"), table_name="future_scenarios")
    op.drop_table("future_scenarios")
    op.drop_index(op.f("ix_future_runs_created_at"), table_name="future_runs")
    op.drop_index(op.f("ix_future_runs_user_id"), table_name="future_runs")
    op.drop_table("future_runs")
