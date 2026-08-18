"""add immutable adapter manifests and local preflights

Revision ID: 20260818_0011
Revises: 20260818_0010
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0011"
down_revision = "20260818_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_adapter_manifests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("adapter_id", sa.String(length=96), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("supported_action_types", sa.JSON(), nullable=False),
        sa.Column("reversible_only", sa.Boolean(), nullable=False),
        sa.Column("supports_idempotency", sa.Boolean(), nullable=False),
        sa.Column("supports_rollback", sa.Boolean(), nullable=False),
        sa.Column("side_effect_free_preflight", sa.Boolean(), nullable=False),
        sa.Column("external_dispatch_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("contract_hash", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adapter_id", "version", name="uq_execution_adapter_version"),
        sa.UniqueConstraint("contract_hash"),
    )
    for column in (
        "adapter_id", "version", "audience", "external_dispatch_enabled", "status",
        "contract_hash", "created_at",
    ):
        op.create_index(
            op.f(f"ix_execution_adapter_manifests_{column}"),
            "execution_adapter_manifests",
            [column],
            unique=(column == "contract_hash"),
        )

    op.create_table(
        "adapter_preflights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dry_run_id", sa.Integer(), nullable=False),
        sa.Column("adapter_manifest_id", sa.Integer(), nullable=False),
        sa.Column("preflight_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=96), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("adapter_contract_hash", sa.String(length=80), nullable=False),
        sa.Column("rollback_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_probe_performed", sa.Boolean(), nullable=False),
        sa.Column("external_dispatch", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dry_run_id"], ["execution_dry_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["adapter_manifest_id"], ["execution_adapter_manifests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adapter_manifest_id", "idempotency_key", name="uq_adapter_preflight_idempotency"),
        sa.UniqueConstraint("preflight_id"),
    )
    for column in (
        "user_id", "dry_run_id", "adapter_manifest_id", "preflight_id", "idempotency_key",
        "audience", "action_type", "action_fingerprint", "adapter_contract_hash",
        "rollback_fingerprint", "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_adapter_preflights_{column}"),
            "adapter_preflights",
            [column],
            unique=(column == "preflight_id"),
        )


def downgrade() -> None:
    for column in reversed((
        "user_id", "dry_run_id", "adapter_manifest_id", "preflight_id", "idempotency_key",
        "audience", "action_type", "action_fingerprint", "adapter_contract_hash",
        "rollback_fingerprint", "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_adapter_preflights_{column}"), table_name="adapter_preflights")
    op.drop_table("adapter_preflights")

    for column in reversed((
        "adapter_id", "version", "audience", "external_dispatch_enabled", "status",
        "contract_hash", "created_at",
    )):
        op.drop_index(op.f(f"ix_execution_adapter_manifests_{column}"), table_name="execution_adapter_manifests")
    op.drop_table("execution_adapter_manifests")
