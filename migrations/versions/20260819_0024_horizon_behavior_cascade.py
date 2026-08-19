"""add HORIZON collective behavior cascade projections

Revision ID: 20260819_0024
Revises: 20260819_0023
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0024"
down_revision = "20260819_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_behavior_cascades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cascade_key", sa.String(length=96), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("stage_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("current_stage_index", sa.Float(), nullable=False),
        sa.Column("current_stage", sa.String(length=255), nullable=False),
        sa.Column("next_stage", sa.String(length=255), nullable=False),
        sa.Column("propagation_score", sa.Float(), nullable=False),
        sa.Column("acceleration_score", sa.Float(), nullable=False),
        sa.Column("evidence_diversity_score", sa.Float(), nullable=False),
        sa.Column("confidence_band", sa.String(length=24), nullable=False),
        sa.Column("probability_basis", sa.String(length=64), nullable=False),
        sa.Column("interpretation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cascade_key", name="uq_horizon_behavior_cascade_key"),
    )
    for column in (
        "cascade_key", "event_id", "pattern_id", "mode", "as_of",
        "confidence_band", "created_at",
    ):
        op.create_index(
            op.f(f"ix_horizon_behavior_cascades_{column}"),
            "horizon_behavior_cascades",
            [column],
            unique=(column == "cascade_key"),
        )


def downgrade() -> None:
    for column in reversed((
        "cascade_key", "event_id", "pattern_id", "mode", "as_of",
        "confidence_band", "created_at",
    )):
        op.drop_index(
            op.f(f"ix_horizon_behavior_cascades_{column}"),
            table_name="horizon_behavior_cascades",
        )
    op.drop_table("horizon_behavior_cascades")
