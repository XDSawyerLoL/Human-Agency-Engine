"""add trusted sandbox runners and signed adapter attestations

Revision ID: 20260818_0012
Revises: 20260818_0011
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0012"
down_revision = "20260818_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sandbox_runner_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("runner_id", sa.String(length=96), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("public_key_b64", sa.String(length=128), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runner_id"),
        sa.UniqueConstraint("key_fingerprint"),
    )
    for column in ("runner_id", "key_fingerprint", "status", "created_at", "revoked_at"):
        op.create_index(
            op.f(f"ix_sandbox_runner_identities_{column}"),
            "sandbox_runner_identities",
            [column],
            unique=(column in {"runner_id", "key_fingerprint"}),
        )

    op.create_table(
        "adapter_sandbox_attestations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("adapter_manifest_id", sa.Integer(), nullable=False),
        sa.Column("runner_identity_id", sa.Integer(), nullable=False),
        sa.Column("attestation_id", sa.String(length=64), nullable=False),
        sa.Column("runner_run_id", sa.String(length=128), nullable=False),
        sa.Column("suite_version", sa.String(length=64), nullable=False),
        sa.Column("adapter_contract_hash", sa.String(length=80), nullable=False),
        sa.Column("evidence_hash", sa.String(length=80), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("initial_state_hash", sa.String(length=80), nullable=False),
        sa.Column("post_preflight_state_hash", sa.String(length=80), nullable=False),
        sa.Column("first_result_hash", sa.String(length=80), nullable=False),
        sa.Column("repeat_result_hash", sa.String(length=80), nullable=False),
        sa.Column("post_first_state_hash", sa.String(length=80), nullable=False),
        sa.Column("post_repeat_state_hash", sa.String(length=80), nullable=False),
        sa.Column("partial_failure_before_hash", sa.String(length=80), nullable=False),
        sa.Column("partial_failure_after_hash", sa.String(length=80), nullable=False),
        sa.Column("rollback_state_hash", sa.String(length=80), nullable=False),
        sa.Column("preflight_no_side_effect", sa.Boolean(), nullable=False),
        sa.Column("idempotency_verified", sa.Boolean(), nullable=False),
        sa.Column("partial_failure_safe", sa.Boolean(), nullable=False),
        sa.Column("rollback_restored", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["adapter_manifest_id"], ["execution_adapter_manifests.id"]),
        sa.ForeignKeyConstraint(["runner_identity_id"], ["sandbox_runner_identities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attestation_id"),
        sa.UniqueConstraint("evidence_hash"),
        sa.UniqueConstraint("runner_identity_id", "runner_run_id", name="uq_sandbox_runner_run"),
    )
    for column in (
        "adapter_manifest_id", "runner_identity_id", "attestation_id", "runner_run_id",
        "suite_version", "adapter_contract_hash", "evidence_hash", "status",
        "observed_at", "valid_until", "created_at",
    ):
        op.create_index(
            op.f(f"ix_adapter_sandbox_attestations_{column}"),
            "adapter_sandbox_attestations",
            [column],
            unique=(column in {"attestation_id", "evidence_hash"}),
        )


def downgrade() -> None:
    for column in reversed((
        "adapter_manifest_id", "runner_identity_id", "attestation_id", "runner_run_id",
        "suite_version", "adapter_contract_hash", "evidence_hash", "status",
        "observed_at", "valid_until", "created_at",
    )):
        op.drop_index(op.f(f"ix_adapter_sandbox_attestations_{column}"), table_name="adapter_sandbox_attestations")
    op.drop_table("adapter_sandbox_attestations")

    for column in reversed(("runner_id", "key_fingerprint", "status", "created_at", "revoked_at")):
        op.drop_index(op.f(f"ix_sandbox_runner_identities_{column}"), table_name="sandbox_runner_identities")
    op.drop_table("sandbox_runner_identities")
