"""add AURA personal agent persistent mission runtime

Revision ID: 20260929_0042
Revises: 20260928_0041
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0042"
down_revision = "20260928_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_agent_missions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("goal_hash", sa.String(length=80), nullable=False),
        sa.Column("encrypted_goal", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("autonomy_level", sa.String(length=32), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), nullable=False),
        sa.Column("encrypted_task_payload", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("max_runs", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id"),
    )
    for column in (
        "mission_id",
        "user_id",
        "goal_hash",
        "task_type",
        "autonomy_level",
        "trigger_type",
        "status",
        "next_run_at",
        "last_run_at",
        "created_at",
    ):
        op.create_index(
            f"ix_personal_agent_missions_{column}",
            "personal_agent_missions",
            [column],
            unique=False,
        )

    op.create_table(
        "personal_agent_mission_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("external_dispatch", sa.Boolean(), nullable=False),
        sa.Column("authorization_required", sa.Boolean(), nullable=False),
        sa.Column("software_agent_run_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["personal_agent_missions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            name="uq_personal_agent_mission_run_id",
        ),
    )
    for column in (
        "run_id",
        "mission_id",
        "trigger",
        "status",
        "software_agent_run_id",
        "started_at",
        "completed_at",
    ):
        op.create_index(
            f"ix_personal_agent_mission_runs_{column}",
            "personal_agent_mission_runs",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("personal_agent_mission_runs")
    op.drop_table("personal_agent_missions")
