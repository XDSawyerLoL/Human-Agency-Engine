"""add event sourced world model and experiments

Revision ID: 20260818_0005
Revises: 20260818_0004
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0005"
down_revision = "20260818_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("causation_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
    )
    for column in ("user_id", "event_type", "source", "occurred_at", "recorded_at", "causation_id", "correlation_id", "event_hash"):
        op.create_index(op.f(f"ix_world_events_{column}"), "world_events", [column], unique=(column == "event_hash"))

    op.create_table(
        "world_hypotheses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cause_pattern", sa.JSON(), nullable=False),
        sa.Column("effect_pattern", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("direction", sa.String(length=24), nullable=False),
        sa.Column("claim_level", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("inconclusive_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "claim_level", "status"):
        op.create_index(op.f(f"ix_world_hypotheses_{column}"), "world_hypotheses", [column], unique=False)

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("hypothesis_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("intervention", sa.JSON(), nullable=False),
        sa.Column("expected_effects", sa.JSON(), nullable=False),
        sa.Column("stop_conditions", sa.JSON(), nullable=False),
        sa.Column("rollback_plan", sa.JSON(), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("authorization_status", sa.String(length=24), nullable=False),
        sa.Column("execution_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["future_scenarios.id"]),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["world_hypotheses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "scenario_id", "hypothesis_id", "reversible", "authorization_status", "execution_status"):
        op.create_index(op.f(f"ix_experiments_{column}"), "experiments", [column], unique=False)

    op.create_table(
        "experiment_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("verdict", sa.String(length=24), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("experiment_id", "verdict", "observed_at"):
        op.create_index(op.f(f"ix_experiment_observations_{column}"), "experiment_observations", [column], unique=False)

    op.create_table(
        "hypothesis_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hypothesis_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("experiment_id", sa.Integer(), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.String(length=24), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["world_hypotheses.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["world_events.id"]),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["experiment_observations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("hypothesis_id", "event_id", "experiment_id", "observation_id", "verdict"):
        op.create_index(op.f(f"ix_hypothesis_evidence_{column}"), "hypothesis_evidence", [column], unique=False)


def downgrade() -> None:
    for column in reversed(("hypothesis_id", "event_id", "experiment_id", "observation_id", "verdict")):
        op.drop_index(op.f(f"ix_hypothesis_evidence_{column}"), table_name="hypothesis_evidence")
    op.drop_table("hypothesis_evidence")
    for column in reversed(("experiment_id", "verdict", "observed_at")):
        op.drop_index(op.f(f"ix_experiment_observations_{column}"), table_name="experiment_observations")
    op.drop_table("experiment_observations")
    for column in reversed(("user_id", "scenario_id", "hypothesis_id", "reversible", "authorization_status", "execution_status")):
        op.drop_index(op.f(f"ix_experiments_{column}"), table_name="experiments")
    op.drop_table("experiments")
    for column in reversed(("user_id", "claim_level", "status")):
        op.drop_index(op.f(f"ix_world_hypotheses_{column}"), table_name="world_hypotheses")
    op.drop_table("world_hypotheses")
    for column in reversed(("user_id", "event_type", "source", "occurred_at", "recorded_at", "causation_id", "correlation_id", "event_hash")):
        op.drop_index(op.f(f"ix_world_events_{column}"), table_name="world_events")
    op.drop_table("world_events")
