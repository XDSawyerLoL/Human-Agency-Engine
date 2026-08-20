"""add HORIZON calibration corpus builder state

Revision ID: 20260820_0039
Revises: 20260820_0038
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0039"
down_revision = "20260820_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horizon_calibration_corpus_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("corpus_key", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=96), nullable=False),
        sa.Column("requested_start_at", sa.DateTime(), nullable=False),
        sa.Column("requested_end_at", sa.DateTime(), nullable=False),
        sa.Column("slice_days", sa.Integer(), nullable=False),
        sa.Column("outcome_grace_days", sa.Integer(), nullable=False),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("summary_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("corpus_key", name="uq_horizon_calibration_corpus_key"),
    )
    for column in (
        "corpus_key", "user_id", "engine_version", "requested_start_at", "requested_end_at",
        "status", "created_at", "updated_at",
    ):
        op.create_index(
            f"ix_horizon_calibration_corpus_runs_{column}",
            "horizon_calibration_corpus_runs",
            [column],
            unique=column == "corpus_key",
        )

    op.create_table(
        "horizon_calibration_corpus_slices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slice_key", sa.String(length=96), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("slice_index", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("meteo_result", sa.JSON(), nullable=False),
        sa.Column("rte_result", sa.JSON(), nullable=False),
        sa.Column("backtest_result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["horizon_calibration_corpus_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "slice_index", name="uq_horizon_calibration_corpus_run_slice"),
        sa.UniqueConstraint("slice_key", name="uq_horizon_calibration_corpus_slice_key"),
    )
    for column in (
        "slice_key", "run_id", "slice_index", "start_at", "end_at", "evaluation_as_of",
        "status", "started_at", "completed_at", "created_at", "updated_at",
    ):
        op.create_index(
            f"ix_horizon_calibration_corpus_slices_{column}",
            "horizon_calibration_corpus_slices",
            [column],
            unique=column == "slice_key",
        )


def downgrade() -> None:
    op.drop_table("horizon_calibration_corpus_slices")
    op.drop_table("horizon_calibration_corpus_runs")
