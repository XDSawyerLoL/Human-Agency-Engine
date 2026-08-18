"""add temporal self state graph

Revision ID: 20260818_0003
Revises: 20260818_0002
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0003"
down_revision = "20260818_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "state_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("superseded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "domain", "key", "source", "sensitivity", "observed_at", "expires_at", "superseded"):
        op.create_index(op.f(f"ix_state_facts_{column}"), "state_facts", [column], unique=False)


def downgrade() -> None:
    for column in reversed(("user_id", "domain", "key", "source", "sensitivity", "observed_at", "expires_at", "superseded")):
        op.drop_index(op.f(f"ix_state_facts_{column}"), table_name="state_facts")
    op.drop_table("state_facts")
