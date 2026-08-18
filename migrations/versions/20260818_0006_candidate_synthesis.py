"""add candidate intervention synthesis

Revision ID: 20260818_0006
Revises: 20260818_0005
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0006"
down_revision = "20260818_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_interventions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_key", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("source_opportunity_id", sa.Integer(), nullable=True),
        sa.Column("hypothesis_ids", sa.JSON(), nullable=False),
        sa.Column("intent_ids", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("intervention", sa.JSON(), nullable=False),
        sa.Column("effects", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=False),
        sa.Column("future_run_id", sa.Integer(), nullable=True),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("decision_status", sa.String(length=64), nullable=False),
        sa.Column("surfaced_opportunity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["future_run_id"], ["future_runs.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["future_scenarios.id"]),
        sa.ForeignKeyConstraint(["surfaced_opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "candidate_key", name="uq_candidate_user_key"),
    )
    for column in (
        "user_id", "candidate_key", "source_type", "source_ref", "source_opportunity_id",
        "status", "future_run_id", "scenario_id", "decision_status", "surfaced_opportunity_id",
    ):
        op.create_index(op.f(f"ix_candidate_interventions_{column}"), "candidate_interventions", [column], unique=False)


def downgrade() -> None:
    for column in reversed((
        "user_id", "candidate_key", "source_type", "source_ref", "source_opportunity_id",
        "status", "future_run_id", "scenario_id", "decision_status", "surfaced_opportunity_id",
    )):
        op.drop_index(op.f(f"ix_candidate_interventions_{column}"), table_name="candidate_interventions")
    op.drop_table("candidate_interventions")
