"""add information acquisition needs

Revision ID: 20260818_0007
Revises: 20260818_0006
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0007"
down_revision = "20260818_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "information_needs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("future_run_id", sa.Integer(), nullable=True),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("need_key", sa.String(length=64), nullable=False),
        sa.Column("need_type", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("acquisition_mode", sa.String(length=32), nullable=False),
        sa.Column("preferred_sources", sa.JSON(), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("blocks_candidate", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=False),
        sa.Column("resolution_source", sa.String(length=64), nullable=False),
        sa.Column("resolution_provenance", sa.JSON(), nullable=False),
        sa.Column("resolution_confidence", sa.Float(), nullable=False),
        sa.Column("ask_count", sa.Integer(), nullable=False),
        sa.Column("last_asked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["future_run_id"], ["future_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["future_scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "need_key", name="uq_information_need_user_key"),
    )
    for column in (
        "user_id", "candidate_id", "future_run_id", "scenario_id", "need_key",
        "need_type", "priority", "acquisition_mode", "sensitivity", "blocks_candidate",
        "status", "last_asked_at",
    ):
        op.create_index(op.f(f"ix_information_needs_{column}"), "information_needs", [column], unique=False)


def downgrade() -> None:
    for column in reversed((
        "user_id", "candidate_id", "future_run_id", "scenario_id", "need_key",
        "need_type", "priority", "acquisition_mode", "sensitivity", "blocks_candidate",
        "status", "last_asked_at",
    )):
        op.drop_index(op.f(f"ix_information_needs_{column}"), table_name="information_needs")
    op.drop_table("information_needs")
