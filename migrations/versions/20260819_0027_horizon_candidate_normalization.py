"""add provenance-bound normalized facts to HORIZON candidates

Revision ID: 20260819_0027
Revises: 20260819_0026
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0027"
down_revision = "20260819_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("horizon_event_candidates") as batch_op:
        batch_op.add_column(sa.Column("normalized_facts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column("normalizer_version", sa.String(length=96), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("horizon_event_candidates") as batch_op:
        batch_op.drop_column("normalizer_version")
        batch_op.drop_column("normalized_facts")
