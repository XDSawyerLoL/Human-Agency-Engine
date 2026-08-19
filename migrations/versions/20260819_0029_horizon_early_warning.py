"""add HORIZON early warning episodes and snapshots

Revision ID: 20260819_0029
Revises: 20260819_0028
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0029"
down_revision = "20260819_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_early_warning_episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_key", sa.String(length=96), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("current_band", sa.String(length=32), nullable=False),
        sa.Column("current_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_key", name="uq_horizon_early_warning_episode_key"),
    )
    for column in ("episode_key", "event_id", "pattern_id", "mode", "opened_at", "current_band", "status", "created_at", "updated_at"):
        op.create_index(
            f"ix_horizon_early_warning_episodes_{column}",
            "horizon_early_warning_episodes",
            [column],
            unique=column == "episode_key",
        )

    op.create_table(
        "horizon_early_warning_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_key", sa.String(length=96), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("input_hash", sa.String(length=96), nullable=False),
        sa.Column("signal_families", sa.JSON(), nullable=False),
        sa.Column("family_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("convergence_score", sa.Float(), nullable=False),
        sa.Column("convergence_band", sa.String(length=32), nullable=False),
        sa.Column("cascade_stage", sa.String(length=255), nullable=False),
        sa.Column("expected_onset_low", sa.DateTime(), nullable=True),
        sa.Column("expected_onset_high", sa.DateTime(), nullable=True),
        sa.Column("remaining_lead_low_hours", sa.Float(), nullable=True),
        sa.Column("remaining_lead_high_hours", sa.Float(), nullable=True),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("interpretation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["horizon_early_warning_episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_key", name="uq_horizon_early_warning_snapshot_key"),
    )
    for column in ("snapshot_key", "episode_id", "as_of", "input_hash", "convergence_band", "created_at"):
        op.create_index(
            f"ix_horizon_early_warning_snapshots_{column}",
            "horizon_early_warning_snapshots",
            [column],
            unique=column == "snapshot_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_early_warning_snapshots")
    op.drop_table("horizon_early_warning_episodes")
