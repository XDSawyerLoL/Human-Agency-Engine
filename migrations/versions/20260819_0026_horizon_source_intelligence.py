"""add HORIZON source intelligence registry and provenance

Revision ID: 20260819_0026
Revises: 20260819_0025
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0026"
down_revision = "20260819_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_class", sa.String(length=48), nullable=False),
        sa.Column("adapter_kind", sa.String(length=64), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("base_locator", sa.Text(), nullable=False),
        sa.Column("trust_weight", sa.Float(), nullable=False),
        sa.Column("refresh_seconds", sa.Integer(), nullable=False),
        sa.Column("requires_credentials", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_horizon_source_key"),
    )
    for column in ("source_key", "source_class", "adapter_kind", "enabled"):
        op.create_index(op.f(f"ix_horizon_sources_{column}"), "horizon_sources", [column], unique=(column == "source_key"))

    op.create_table(
        "horizon_raw_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_key", sa.String(length=192), nullable=False),
        sa.Column("observation_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("canonical_facts", sa.JSON(), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=80), nullable=False),
        sa.Column("event_time", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["horizon_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_key", name="uq_horizon_observation_source_external"),
    )
    for column in ("source_id", "external_key", "observation_type", "payload_hash", "event_time", "published_at", "observed_at"):
        op.create_index(op.f(f"ix_horizon_raw_observations_{column}"), "horizon_raw_observations", [column], unique=False)

    op.create_table(
        "horizon_event_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_key", sa.String(length=96), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("corroborating_observation_ids", sa.JSON(), nullable=False),
        sa.Column("source_classes", sa.JSON(), nullable=False),
        sa.Column("corroboration_score", sa.Float(), nullable=False),
        sa.Column("promotion_status", sa.String(length=32), nullable=False),
        sa.Column("promoted_event_id", sa.Integer(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["promoted_event_id"], ["horizon_global_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_key", name="uq_horizon_event_candidate_key"),
    )
    for column in ("candidate_key", "event_type", "promotion_status", "promoted_event_id", "first_observed_at", "last_observed_at"):
        op.create_index(op.f(f"ix_horizon_event_candidates_{column}"), "horizon_event_candidates", [column], unique=(column == "candidate_key"))


def downgrade() -> None:
    for column in reversed(("candidate_key", "event_type", "promotion_status", "promoted_event_id", "first_observed_at", "last_observed_at")):
        op.drop_index(op.f(f"ix_horizon_event_candidates_{column}"), table_name="horizon_event_candidates")
    op.drop_table("horizon_event_candidates")
    for column in reversed(("source_id", "external_key", "observation_type", "payload_hash", "event_time", "published_at", "observed_at")):
        op.drop_index(op.f(f"ix_horizon_raw_observations_{column}"), table_name="horizon_raw_observations")
    op.drop_table("horizon_raw_observations")
    for column in reversed(("source_key", "source_class", "adapter_kind", "enabled")):
        op.drop_index(op.f(f"ix_horizon_sources_{column}"), table_name="horizon_sources")
    op.drop_table("horizon_sources")
