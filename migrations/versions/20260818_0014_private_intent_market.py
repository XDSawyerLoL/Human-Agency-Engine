"""add private intent envelopes and signed market offers

Revision ID: 20260818_0014
Revises: 20260818_0013
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260818_0014"
down_revision = "20260818_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "private_intent_envelopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("envelope_id", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=64), nullable=False),
        sa.Column("request_type", sa.String(length=24), nullable=False),
        sa.Column("category", sa.String(length=96), nullable=False),
        sa.Column("disclosure", sa.JSON(), nullable=False),
        sa.Column("ranking_policy", sa.JSON(), nullable=False),
        sa.Column("mandate_version", sa.Integer(), nullable=False),
        sa.Column("candidate_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("challenge_nonce", sa.String(length=64), nullable=False),
        sa.Column("envelope_hash", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_interventions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("envelope_id"),
        sa.UniqueConstraint("subject_ref"),
        sa.UniqueConstraint("challenge_nonce"),
        sa.UniqueConstraint("envelope_hash"),
    )
    for column in (
        "user_id", "candidate_id", "envelope_id", "subject_ref", "request_type", "category",
        "mandate_version", "candidate_fingerprint", "challenge_nonce", "envelope_hash", "status",
        "expires_at", "created_at", "revoked_at",
    ):
        op.create_index(
            op.f(f"ix_private_intent_envelopes_{column}"),
            "private_intent_envelopes",
            [column],
            unique=(column in {"envelope_id", "subject_ref", "challenge_nonce", "envelope_hash"}),
        )

    op.create_table(
        "market_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("envelope_db_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.String(length=96), nullable=False),
        sa.Column("responder_id", sa.String(length=80), nullable=False),
        sa.Column("responder_label", sa.String(length=255), nullable=False),
        sa.Column("public_key_b64", sa.String(length=128), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("offer_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("eligibility", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["envelope_db_id"], ["private_intent_envelopes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id"),
        sa.UniqueConstraint("offer_hash"),
    )
    for column in (
        "envelope_db_id", "offer_id", "responder_id", "offer_hash", "status", "created_at",
    ):
        op.create_index(
            op.f(f"ix_market_offers_{column}"),
            "market_offers",
            [column],
            unique=(column in {"offer_id", "offer_hash"}),
        )


def downgrade() -> None:
    for column in reversed((
        "envelope_db_id", "offer_id", "responder_id", "offer_hash", "status", "created_at",
    )):
        op.drop_index(op.f(f"ix_market_offers_{column}"), table_name="market_offers")
    op.drop_table("market_offers")

    for column in reversed((
        "user_id", "candidate_id", "envelope_id", "subject_ref", "request_type", "category",
        "mandate_version", "candidate_fingerprint", "challenge_nonce", "envelope_hash", "status",
        "expires_at", "created_at", "revoked_at",
    )):
        op.drop_index(op.f(f"ix_private_intent_envelopes_{column}"), table_name="private_intent_envelopes")
    op.drop_table("private_intent_envelopes")
