"""add AURA sandboxed software-engine run ledger

Revision ID: 20260928_0041
Revises: 20260825_0040
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0041"
down_revision = "20260825_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "software_agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("adapter_preflight_id", sa.Integer(), nullable=False),
        sa.Column("adapter_manifest_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("workspace_path", sa.String(length=1024), nullable=False),
        sa.Column("goal_hash", sa.String(length=80), nullable=False),
        sa.Column("quality_commands", sa.JSON(), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("worktree_required", sa.Boolean(), nullable=False),
        sa.Column("external_dispatch", sa.Boolean(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("execution_status", sa.String(length=48), nullable=True),
        sa.Column("final_response_hash", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("launched_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["adapter_manifest_id"], ["execution_adapter_manifests.id"]),
        sa.ForeignKeyConstraint(
            ["adapter_preflight_id"],
            ["adapter_preflights.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_software_agent_run_idempotency_key",
        ),
        sa.UniqueConstraint("run_id"),
    )
    for column in (
        "run_id",
        "idempotency_key",
        "user_id",
        "adapter_preflight_id",
        "adapter_manifest_id",
        "repository",
        "goal_hash",
        "conversation_id",
        "status",
        "execution_status",
        "launched_at",
        "last_checked_at",
        "completed_at",
        "created_at",
    ):
        op.create_index(
            f"ix_software_agent_runs_{column}",
            "software_agent_runs",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("software_agent_runs")
