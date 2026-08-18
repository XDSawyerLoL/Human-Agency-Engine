from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import User
from app.payment_intent_models import PaymentIntentCapability, PaymentIntentCapabilityUse
from tests.test_post_allocation_acceptance import _accept, _private_allocation
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group
from tests.test_selective_disclosure_vault import _prepared_user

client = TestClient(app)


def _preview(uid: str, permit_id: str, audience: str = "payment-preparer:test-adapter"):
    return client.post(
        f"/v1/payment-intents/users/{uid}/preview",
        json={"settlement_permit_id": permit_id, "audience": audience},
    )


def _issue(uid: str, permit_id: str, preview: dict):
    return client.post(
        f"/v1/payment-intents/users/{uid}",
        json={
            "settlement_permit_id": permit_id,
            "audience": preview["audience"],
            "expires_in_seconds": 600,
            "confirm": preview["confirm"],
        },
    )


def test_preview_derives_exact_amount_and_explicitly_grants_no_debit_authority():
    uid, private, decision, permit = _prepared_user("payment-intent-preview")
    preview = _preview(uid, permit["permit"]["permit_id"])
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["allocated_quantity"] == private["allocated_quantity"] == 1
    assert body["unit_price"] == decision["unit_price"] == 70.0
    assert body["currency"] == "EUR"
    assert body["exact_total_amount"] == 70.0
    assert body["payment_terms_hash"].startswith("sha256:")
    assert body["confirm"] == (
        f"ISSUE PAYMENT INTENT {permit['permit']['permit_id']} "
        f"{body['payment_terms_hash'][-12:]}"
    )
    assert body["restrictions"] == {
        "debit_allowed": False,
        "capture_allowed": False,
        "funds_movement_allowed": False,
        "payment_instrument_access": False,
        "order_creation_allowed": False,
        "external_dispatch": False,
    }
    assert body["payment_instrument_required"] is False
    assert body["payment_instrument_disclosed"] is False
    assert body["funds_moved"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False


def test_signed_capability_contains_exact_terms_but_no_payment_instrument_or_identity():
    uid, _, _, permit = _prepared_user("payment-intent-minimal-proof")
    preview = _preview(uid, permit["permit"]["permit_id"]).json()
    issued = _issue(uid, permit["permit"]["permit_id"], preview)
    assert issued.status_code == 200, issued.text
    body = issued.json()
    claims = body["proof"]["claims"]
    assert claims["protocol"] == "hae-payment-intent-capability-v1"
    assert claims["capability"] == "prepare_payment_intent"
    assert claims["payment_terms"]["exact_total_amount"] == 70.0
    assert claims["payment_terms"]["currency"] == "EUR"
    assert claims["restrictions"]["debit_allowed"] is False
    assert claims["restrictions"]["capture_allowed"] is False
    assert claims["restrictions"]["funds_movement_allowed"] is False
    assert claims["restrictions"]["payment_instrument_access"] is False
    assert claims["restrictions"]["order_creation_allowed"] is False
    assert claims["restrictions"]["external_dispatch"] is False
    assert claims["sub"] != uid

    serialized = str(body).lower()
    for forbidden in (
        uid.lower(),
        "card_number",
        "payment_method",
        "iban",
        "bank_account",
        "address_line1",
        "email",
        "phone",
    ):
        assert forbidden not in serialized
    assert body["debit_allowed"] is False
    assert body["funds_movement_allowed"] is False
    assert body["payment_instrument_access"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False

    db = SessionLocal()
    try:
        row = db.query(PaymentIntentCapability).filter(
            PaymentIntentCapability.capability_id == body["capability"]["capability_id"]
        ).one()
        assert row.token_hash.startswith("sha256:")
        assert body["proof"]["token"] not in row.token_hash
        assert row.status == "active"
        assert row.use_count == 0
    finally:
        db.close()

    columns = {column["name"] for column in inspect(engine).get_columns("payment_intent_capabilities")}
    assert "token" not in columns
    assert "token_hash" in columns
    assert "card_number" not in columns
    assert "payment_method" not in columns
    assert "bank_account" not in columns


def test_capability_is_exact_audience_bound_and_one_time_prepare_only():
    uid, _, _, permit = _prepared_user("payment-intent-one-time")
    preview = _preview(uid, permit["permit"]["permit_id"], "payment-preparer:adapter-a").json()
    issued = _issue(uid, permit["permit"]["permit_id"], preview)
    assert issued.status_code == 200, issued.text
    proof = issued.json()["proof"]

    verified = client.post(
        "/v1/payment-intents/verify",
        json={"token": proof["token"], "audience": "payment-preparer:adapter-a"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["valid"] is True
    assert verified.json()["debit_allowed"] is False
    assert verified.json()["capture_allowed"] is False
    assert verified.json()["funds_movement_allowed"] is False
    assert verified.json()["payment_instrument_access"] is False
    assert verified.json()["external_dispatch"] is False

    wrong = client.post(
        "/v1/payment-intents/verify",
        json={"token": proof["token"], "audience": "payment-preparer:adapter-b"},
    )
    assert wrong.status_code == 400
    assert "audience" in wrong.text.lower()

    consumed = client.post(
        "/v1/payment-intents/consume",
        json={
            "token": proof["token"],
            "audience": "payment-preparer:adapter-a",
            "request_id": "payment-intent-prepare-request-0001",
        },
    )
    assert consumed.status_code == 200, consumed.text
    assert consumed.json()["effect"] == "prepare_payment_intent_only"
    assert consumed.json()["debit_allowed"] is False
    assert consumed.json()["funds_movement_allowed"] is False
    assert consumed.json()["payment_instrument_access"] is False
    assert consumed.json()["payment_created"] is False
    assert consumed.json()["order_created"] is False

    second = client.post(
        "/v1/payment-intents/consume",
        json={
            "token": proof["token"],
            "audience": "payment-preparer:adapter-a",
            "request_id": "payment-intent-prepare-request-0002",
        },
    )
    assert second.status_code == 400

    db = SessionLocal()
    try:
        row = db.query(PaymentIntentCapability).filter(
            PaymentIntentCapability.capability_id == issued.json()["capability"]["capability_id"]
        ).one()
        assert row.status == "consumed"
        assert row.use_count == 1
        assert row.consumed_at is not None
        assert db.query(PaymentIntentCapabilityUse).filter(
            PaymentIntentCapabilityUse.capability_db_id == row.id
        ).count() == 1
    finally:
        db.close()


def test_unconsumed_settlement_permit_and_wildcard_audience_are_rejected():
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    members, offer, _ = _prepared_oversubscribed_group(
        "payment-intent-parent-required", users=10, quantity=1, capacity=10
    )
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    decisions = []
    for uid, _, _ in members:
        private = _private_allocation(uid)
        accepted = _accept(uid, private, allocation_set_hash)
        assert accepted.status_code == 200
        decisions.append((uid, private, accepted.json()))
    assert client.post(
        "/v1/collective-settlement/assess", json={"offer_id": offer["offer_id"]}
    ).json()["settlement_ready"] is True

    uid, private, decision = decisions[0]
    permit = client.post(
        f"/v1/settlement-permits/users/{uid}",
        json={
            "allocation_entry_id": private["allocation_entry_id"],
            "expires_in_seconds": 900,
            "confirm": (
                f"ISSUE SETTLEMENT PERMIT {private['allocation_entry_id']} "
                f"{decision['decision_hash'][-12:]}"
            ),
        },
    )
    assert permit.status_code == 200
    permit_id = permit.json()["permit"]["permit_id"]

    blocked = _preview(uid, permit_id)
    assert blocked.status_code == 400
    assert "must be consumed" in blocked.text.lower()

    consumed = client.post(
        "/v1/settlement-permits/consume",
        json={
            "token": permit.json()["proof"]["token"],
            "audience": permit.json()["proof"]["claims"]["aud"],
            "request_id": "prepare-parent-payment-intent-0001",
        },
    )
    assert consumed.status_code == 200

    wildcard = _preview(uid, permit_id, "payment-preparer:*")
    assert wildcard.status_code == 400
    assert "exact adapter" in wildcard.text.lower()
    wrong_scheme = _preview(uid, permit_id, "merchant:adapter-a")
    assert wrong_scheme.status_code == 400
    assert "payment-preparer" in wrong_scheme.text.lower()


def test_mandate_change_invalidates_unconsumed_payment_intent_capability():
    uid, _, _, permit = _prepared_user("payment-intent-mandate-change")
    preview = _preview(uid, permit["permit"]["permit_id"]).json()
    issued = _issue(uid, permit["permit"]["permit_id"], preview)
    assert issued.status_code == 200
    proof = issued.json()["proof"]

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Pause payment preparation.",
            "principles": ["manual only"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200

    verify = client.post(
        "/v1/payment-intents/verify",
        json={"token": proof["token"], "audience": proof["claims"]["aud"]},
    )
    assert verify.status_code == 400
    text = verify.text.lower()
    assert "mandate" in text or "private intent" in text or "settlement" in text
