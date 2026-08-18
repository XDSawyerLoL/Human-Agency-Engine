"""add policy receipts human commits and execution dry runs

Revision ID: 20260818_0009
Revises: 20260818_0008
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0009"
down_revision = "20260818_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_constraints", sa.JSON(), nullable=False),
        sa.Column("receipt_hash", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id"),
        sa.UniqueConstraint("receipt_hash"),
    )
    for column in (
        "user_id", "candidate_id", "receipt_id", "engine_version", "mandate_version",
        "capability", "audience", "action_fingerprint", "decision", "receipt_hash", "created_at",
    ):
        op.create_index(
            op.f(f"ix_policy_receipts_{column}"),
            "policy_receipts",
            [column],
            unique=(column in {"receipt_id", "receipt_hash"}),
        )

    op.create_table(
        "human_commit_authorizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("policy_receipt_id", sa.Integer(), nullable=False),
        sa.Column("commit_id", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=96), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("exact_action", sa.JSON(), nullable=False),
        sa.Column("rollback_plan", sa.Text(), nullable=False),
        sa.Column("rollback_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("prepared_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_receipt_id"], ["policy_receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("commit_id"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in (
        "user_id", "candidate_id", "policy_receipt_id", "commit_id", "audience",
        "mandate_version", "action_fingerprint", "rollback_fingerprint", "token_hash", "status",
        "prepared_at", "confirmed_at", "expires_at", "consumed_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_human_commit_authorizations_{column}"),
            "human_commit_authorizations",
            [column],
            unique=(column in {"commit_id", "token_hash"}),
        )

    op.create_table(
        "execution_dry_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("human_commit_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("would_execute", sa.Boolean(), nullable=False),
        sa.Column("external_dispatch", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grant_id"], ["delegation_grants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["human_commit_id"], ["human_commit_authorizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    for column in (
        "user_id", "candidate_id", "grant_id", "human_commit_id", "request_id",
        "audience", "action_fingerprint", "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_execution_dry_runs_{column}"),
            "execution_dry_runs",
            [column],
            unique=(column == "request_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "candidate_id", "grant_id", "human_commit_id", "request_id",
        "audience", "action_fingerprint", "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_execution_dry_runs_{column}"), table_name="execution_dry_runs")
    op.drop_table("execution_dry_runs")

    for column in reversed((
        "user_id", "candidate_id", "policy_receipt_id", "commit_id", "audience",
        "mandate_version", "action_fingerprint", "rollback_fingerprint", "token_hash", "status",
        "prepared_at", "confirmed_at", "expires_at", "consumed_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_human_commit_authorizations_{column}"), table_name="human_commit_authorizations")
    op.drop_table("human_commit_authorizations")

    for column in reversed((
        "user_id", "candidate_id", "receipt_id", "engine_version", "mandate_version",
        "capability", "audience", "action_fingerprint", "decision", "receipt_hash", "created_at",
    )):
        op.drop_index(op.f(f"ix_policy_receipts_{column}"), table_name="policy_receipts")
    op.drop_table("policy_receipts")
