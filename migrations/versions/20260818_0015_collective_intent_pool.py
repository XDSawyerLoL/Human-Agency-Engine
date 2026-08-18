"""add privacy-thresholded collective intent cohorts and memberships

Revision ID: 20260818_0015
Revises: 20260818_0014
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0015"
down_revision = "20260818_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_intent_cohorts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cohort_key", sa.String(length=80), nullable=False),
        sa.Column("request_type", sa.String(length=24), nullable=False),
        sa.Column("category", sa.String(length=96), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("minimum_cohort_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cohort_key"),
    )
    for column in (
        "cohort_key", "request_type", "category", "currency", "country", "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_collective_intent_cohorts_{column}"),
            "collective_intent_cohorts",
            [column],
            unique=(column == "cohort_key"),
        )

    op.create_table(
        "collective_intent_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("envelope_db_id", sa.Integer(), nullable=False),
        sa.Column("cohort_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.String(length=64), nullable=False),
        sa.Column("contribution_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["envelope_db_id"], ["private_intent_envelopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cohort_id"], ["collective_intent_cohorts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cohort_id", name="uq_collective_user_cohort"),
        sa.UniqueConstraint("membership_id"),
    )
    for column in (
        "user_id", "envelope_db_id", "cohort_id", "membership_id", "contribution_fingerprint",
        "status", "joined_at", "left_at",
    ):
        op.create_index(
            op.f(f"ix_collective_intent_memberships_{column}"),
            "collective_intent_memberships",
            [column],
            unique=(column == "membership_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "envelope_db_id", "cohort_id", "membership_id", "contribution_fingerprint",
        "status", "joined_at", "left_at",
    )):
        op.drop_index(op.f(f"ix_collective_intent_memberships_{column}"), table_name="collective_intent_memberships")
    op.drop_table("collective_intent_memberships")

    for column in reversed((
        "cohort_key", "request_type", "category", "currency", "country", "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_collective_intent_cohorts_{column}"), table_name="collective_intent_cohorts")
    op.drop_table("collective_intent_cohorts")
