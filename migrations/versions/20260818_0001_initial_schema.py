"""Initial Human Agency Engine schema.

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("monthly_income", sa.Float(), nullable=True),
        sa.Column("monthly_fixed_costs", sa.Float(), nullable=True),
        sa.Column("liquid_cash", sa.Float(), nullable=True),
        sa.Column("minimum_cash_buffer", sa.Float(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_users_external_id", "users", ["external_id"], unique=True)

    op.create_table(
        "intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("target", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_intents_user_id", "intents", ["user_id"])
    op.create_index("ix_intents_kind", "intents", ["kind"])

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_signals_user_id", "signals", ["user_id"])
    op.create_index("ix_signals_source", "signals", ["source"])
    op.create_index("ix_signals_type", "signals", ["type"])
    op.create_index("ix_signals_observed_at", "signals", ["observed_at"])
    op.create_index("ix_signals_processed", "signals", ["processed"])

    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_token_json", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_connector_account_user_provider"),
    )
    op.create_index("ix_connector_accounts_user_id", "connector_accounts", ["user_id"])
    op.create_index("ix_connector_accounts_provider", "connector_accounts", ["provider"])
    op.create_index("ix_connector_accounts_enabled", "connector_accounts", ["enabled"])

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_oauth_states_state_hash", "oauth_states", ["state_hash"], unique=True)
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])
    op.create_index("ix_oauth_states_provider", "oauth_states", ["provider"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])
    op.create_index("ix_oauth_states_consumed", "oauth_states", ["consumed"])

    op.create_table(
        "ingestion_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connector_id", sa.Integer(), sa.ForeignKey("connector_accounts.id"), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=False),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connector_id", "external_key", name="uq_ingestion_connector_external_key"),
    )
    op.create_index("ix_ingestion_records_connector_id", "ingestion_records", ["connector_id"])
    op.create_index("ix_ingestion_records_external_key", "ingestion_records", ["external_key"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("proposed_action", sa.JSON(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("counterfactual", sa.JSON(), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("care_status", sa.String(length=32), nullable=False),
        sa.Column("care_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_opportunities_user_id", "opportunities", ["user_id"])
    op.create_index("ix_opportunities_category", "opportunities", ["category"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("useful", sa.Boolean(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("executed", sa.Boolean(), nullable=True),
        sa.Column("realized_value", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("opportunity_id"),
    )
    op.create_index("ix_outcomes_opportunity_id", "outcomes", ["opportunity_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_outcomes_opportunity_id", table_name="outcomes")
    op.drop_table("outcomes")

    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_category", table_name="opportunities")
    op.drop_index("ix_opportunities_user_id", table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index("ix_ingestion_records_external_key", table_name="ingestion_records")
    op.drop_index("ix_ingestion_records_connector_id", table_name="ingestion_records")
    op.drop_table("ingestion_records")

    op.drop_index("ix_oauth_states_consumed", table_name="oauth_states")
    op.drop_index("ix_oauth_states_expires_at", table_name="oauth_states")
    op.drop_index("ix_oauth_states_provider", table_name="oauth_states")
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_index("ix_oauth_states_state_hash", table_name="oauth_states")
    op.drop_table("oauth_states")

    op.drop_index("ix_connector_accounts_enabled", table_name="connector_accounts")
    op.drop_index("ix_connector_accounts_provider", table_name="connector_accounts")
    op.drop_index("ix_connector_accounts_user_id", table_name="connector_accounts")
    op.drop_table("connector_accounts")

    op.drop_index("ix_signals_processed", table_name="signals")
    op.drop_index("ix_signals_observed_at", table_name="signals")
    op.drop_index("ix_signals_type", table_name="signals")
    op.drop_index("ix_signals_source", table_name="signals")
    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_intents_kind", table_name="intents")
    op.drop_index("ix_intents_user_id", table_name="intents")
    op.drop_table("intents")

    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_table("users")
