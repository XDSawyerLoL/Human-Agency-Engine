"""add execution readiness receipts

Revision ID: 20260818_0013
Revises: 20260818_0012
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0013"
down_revision = "20260818_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_readiness_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("preflight_id", sa.Integer(), nullable=False),
        sa.Column("attestation_id", sa.Integer(), nullable=True),
        sa.Column("policy_receipt_id", sa.Integer(), nullable=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("adapter_contract_hash", sa.String(length=80), nullable=False),
        sa.Column("attestation_evidence_hash", sa.String(length=80), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("external_dispatch_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preflight_id"], ["adapter_preflights.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attestation_id"], ["adapter_sandbox_attestations.id"]),
        sa.ForeignKeyConstraint(["policy_receipt_id"], ["policy_receipts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id"),
    )
    for column in (
        "user_id", "candidate_id", "preflight_id", "attestation_id", "policy_receipt_id",
        "receipt_id", "mandate_version", "action_fingerprint", "adapter_contract_hash",
        "attestation_evidence_hash", "decision", "created_at",
    ):
        op.create_index(
            op.f(f"ix_execution_readiness_receipts_{column}"),
            "execution_readiness_receipts",
            [column],
            unique=(column == "receipt_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "candidate_id", "preflight_id", "attestation_id", "policy_receipt_id",
        "receipt_id", "mandate_version", "action_fingerprint", "adapter_contract_hash",
        "attestation_evidence_hash", "decision", "created_at",
    )):
        op.drop_index(op.f(f"ix_execution_readiness_receipts_{column}"), table_name="execution_readiness_receipts")
    op.drop_table("execution_readiness_receipts")
