"""add HORIZON automatic reevaluation decision ledger

Revision ID: 20260819_0028
Revises: 20260819_0027
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0028"
down_revision = "20260819_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_reevaluation_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_key", sa.String(length=96), nullable=False),
        sa.Column("input_hash", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("scope_status", sa.String(length=24), nullable=False),
        sa.Column("attention_score", sa.Float(), nullable=False),
        sa.Column("attention_band", sa.String(length=24), nullable=False),
        sa.Column("cascade_stage", sa.String(length=255), nullable=False),
        sa.Column("surface_requested", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["horizon_personal_impact_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_key", name="uq_horizon_reevaluation_decision_key"),
    )
    for column in (
        "decision_key",
        "input_hash",
        "user_id",
        "event_id",
        "pattern_id",
        "assessment_id",
        "opportunity_id",
        "notification_id",
        "scope_status",
        "attention_band",
        "surface_requested",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_horizon_reevaluation_decisions_{column}",
            "horizon_reevaluation_decisions",
            [column],
            unique=column == "decision_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_reevaluation_decisions")
