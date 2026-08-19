"""add HORIZON personal impact assessments

Revision ID: 20260819_0025
Revises: 20260819_0024
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0025"
down_revision = "20260819_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_personal_impact_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_key", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=True),
        sa.Column("cascade_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("fact_layer", sa.JSON(), nullable=False),
        sa.Column("collective_behavior_layer", sa.JSON(), nullable=False),
        sa.Column("personal_exposure_layer", sa.JSON(), nullable=False),
        sa.Column("timing_layer", sa.JSON(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("urgency_score", sa.Float(), nullable=False),
        sa.Column("attention_score", sa.Float(), nullable=False),
        sa.Column("attention_band", sa.String(length=24), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["horizon_behavior_patterns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["forecast_id"], ["horizon_forecasts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cascade_id"], ["horizon_behavior_cascades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_key", name="uq_horizon_personal_impact_assessment_key"),
    )
    for column in (
        "assessment_key", "user_id", "event_id", "pattern_id", "forecast_id",
        "cascade_id", "mode", "as_of", "attention_band", "created_at",
    ):
        op.create_index(
            op.f(f"ix_horizon_personal_impact_assessments_{column}"),
            "horizon_personal_impact_assessments",
            [column],
            unique=(column == "assessment_key"),
        )


def downgrade() -> None:
    for column in reversed((
        "assessment_key", "user_id", "event_id", "pattern_id", "forecast_id",
        "cascade_id", "mode", "as_of", "attention_band", "created_at",
    )):
        op.drop_index(
            op.f(f"ix_horizon_personal_impact_assessments_{column}"),
            table_name="horizon_personal_impact_assessments",
        )
    op.drop_table("horizon_personal_impact_assessments")
