"""add personal mandate and proactive notifications

Revision ID: 20260818_0002
Revises: 20260818_0001
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0002"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Paris"),
    )

    op.create_table(
        "personal_mandates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mission", sa.Text(), nullable=False),
        sa.Column("principles", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("autonomy", sa.JSON(), nullable=False),
        sa.Column("notification_policy", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_personal_mandate_user"),
    )
    op.create_index(op.f("ix_personal_mandates_user_id"), "personal_mandates", ["user_id"], unique=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("suppression_reason", sa.Text(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", name="uq_notification_opportunity"),
    )
    op.create_index(op.f("ix_notifications_available_at"), "notifications", ["available_at"], unique=False)
    op.create_index(op.f("ix_notifications_opportunity_id"), "notifications", ["opportunity_id"], unique=True)
    op.create_index(op.f("ix_notifications_status"), "notifications", ["status"], unique=False)
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_status"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_opportunity_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_available_at"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_personal_mandates_user_id"), table_name="personal_mandates")
    op.drop_table("personal_mandates")
    op.drop_column("users", "timezone")
