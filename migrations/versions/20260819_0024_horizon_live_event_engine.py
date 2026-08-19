"""add HORIZON live source ingestion

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
        "horizon_live_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )
    for column in ("source_key", "source_kind", "enabled", "last_success_at"):
        op.create_index(
            op.f(f"ix_horizon_live_sources_{column}"),
            "horizon_live_sources",
            [column],
            unique=(column == "source_key"),
        )

    op.create_table(
        "horizon_live_ingestion_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=96), nullable=False),
        sa.Column("external_key", sa.String(length=192), nullable=False),
        sa.Column("payload_hash", sa.String(length=80), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("provider_observed_at", sa.DateTime(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["horizon_global_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_key",
            "external_key",
            "payload_hash",
            name="uq_horizon_live_source_external_payload",
        ),
    )
    for column in ("source_key", "external_key", "payload_hash", "event_id", "provider_observed_at", "ingested_at"):
        op.create_index(
            op.f(f"ix_horizon_live_ingestion_records_{column}"),
            "horizon_live_ingestion_records",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("horizon_live_ingestion_records")
    op.drop_table("horizon_live_sources")
