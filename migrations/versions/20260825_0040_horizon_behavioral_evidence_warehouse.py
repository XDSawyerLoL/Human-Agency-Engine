"""add HORIZON behavioral evidence warehouse

Revision ID: 20260825_0040
Revises: 20260820_0039
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260825_0040"
down_revision = "20260820_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_behavioral_ingestion_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=96), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("documents_seen", sa.Integer(), nullable=False),
        sa.Column("documents_created", sa.Integer(), nullable=False),
        sa.Column("documents_updated", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_horizon_behavioral_ingestion_run_key"),
    )
    for column in ("run_key", "status", "started_at", "completed_at", "created_at"):
        op.create_index(
            f"ix_horizon_behavioral_ingestion_runs_{column}",
            "horizon_behavioral_ingestion_runs",
            [column],
            unique=column == "run_key",
        )

    op.create_table(
        "horizon_behavioral_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_key", sa.String(length=96), nullable=False),
        sa.Column("source", sa.String(length=48), nullable=False),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("doi", sa.String(length=512), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publication_date", sa.String(length=32), nullable=True),
        sa.Column("work_type", sa.String(length=256), nullable=True),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("open_access", sa.Boolean(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("discovery_signal", sa.Float(), nullable=True),
        sa.Column("abstract_available", sa.Boolean(), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ingestion_count", sa.Integer(), nullable=False),
        sa.Column("evidence_status", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_key", name="uq_horizon_behavioral_document_key"),
        sa.UniqueConstraint("source", "source_record_id", name="uq_horizon_behavioral_document_source_record"),
    )
    for column in (
        "document_key", "source", "source_record_id", "doi", "publication_year", "work_type",
        "open_access", "content_fingerprint", "evidence_status", "first_seen_at", "last_seen_at",
        "created_at", "updated_at",
    ):
        op.create_index(
            f"ix_horizon_behavioral_documents_{column}",
            "horizon_behavioral_documents",
            [column],
            unique=column == "document_key",
        )

    op.create_table(
        "horizon_behavioral_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("effect_key", sa.String(length=96), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("mechanism", sa.String(length=48), nullable=False),
        sa.Column("construct", sa.String(length=160), nullable=False),
        sa.Column("population", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("exposure", sa.Text(), nullable=False),
        sa.Column("behavioral_outcome", sa.Text(), nullable=False),
        sa.Column("effect_direction", sa.String(length=32), nullable=False),
        sa.Column("effect_size", sa.Float(), nullable=True),
        sa.Column("effect_size_type", sa.String(length=64), nullable=True),
        sa.Column("uncertainty_low", sa.Float(), nullable=True),
        sa.Column("uncertainty_high", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("study_design", sa.String(length=64), nullable=False),
        sa.Column("replication_status", sa.String(length=32), nullable=False),
        sa.Column("preregistered", sa.Boolean(), nullable=True),
        sa.Column("peer_reviewed", sa.Boolean(), nullable=True),
        sa.Column("countries", sa.JSON(), nullable=False),
        sa.Column("time_horizon", sa.String(length=160), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.String(length=512), nullable=True),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("extraction_version", sa.String(length=96), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("evidence_status", sa.String(length=32), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["horizon_behavioral_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("effect_key", name="uq_horizon_behavioral_effect_key"),
    )
    for column in (
        "effect_key", "document_id", "mechanism", "construct", "effect_direction", "sample_size",
        "study_design", "replication_status", "extraction_method", "quality_score", "evidence_status",
        "reviewed_at", "created_at", "updated_at",
    ):
        op.create_index(
            f"ix_horizon_behavioral_effects_{column}",
            "horizon_behavioral_effects",
            [column],
            unique=column == "effect_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_behavioral_effects")
    op.drop_table("horizon_behavioral_documents")
    op.drop_table("horizon_behavioral_ingestion_runs")
