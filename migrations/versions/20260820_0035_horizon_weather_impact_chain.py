"""add HORIZON Windy confirmation and weather impact chain ledger

Revision ID: 20260820_0035
Revises: 20260819_0034
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0035"
down_revision = "20260819_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_weather_impact_chains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_key", sa.String(length=96), nullable=False),
        sa.Column("windy_candidate_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_event_id", sa.Integer(), nullable=False),
        sa.Column("regional_event_id", sa.Integer(), nullable=False),
        sa.Column("outcome_signal_id", sa.Integer(), nullable=False),
        sa.Column("windy_first_observed_at", sa.DateTime(), nullable=False),
        sa.Column("official_confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("behavior_observed_at", sa.DateTime(), nullable=False),
        sa.Column("windy_to_official_lead_hours", sa.Float(), nullable=False),
        sa.Column("official_to_behavior_lag_hours", sa.Float(), nullable=False),
        sa.Column("windy_to_behavior_lead_hours", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["windy_candidate_id"], ["horizon_event_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["regional_event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outcome_signal_id"], ["horizon_social_signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_key", name="uq_horizon_weather_impact_chain_key"),
        sa.UniqueConstraint("windy_candidate_id", name="uq_horizon_weather_impact_chain_candidate"),
    )
    for column in (
        "chain_key", "windy_candidate_id", "confirmed_event_id", "regional_event_id",
        "outcome_signal_id", "windy_first_observed_at", "official_confirmed_at",
        "behavior_observed_at", "created_at",
    ):
        op.create_index(
            f"ix_horizon_weather_impact_chains_{column}",
            "horizon_weather_impact_chains",
            [column],
            unique=column in {"chain_key", "windy_candidate_id"},
        )


def downgrade() -> None:
    op.drop_table("horizon_weather_impact_chains")
