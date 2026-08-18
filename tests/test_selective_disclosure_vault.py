from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User
from app.services.vault import _claim_set_hash
from app.vault_models import SelectiveDisclosureGrant, UserVaultClaim
from tests.test_post_allocation_acceptance import _accept, _private_allocation
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group

client = TestClient(app)


def _prepared_user(category: str):
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    members, offer, _ = _prepared_oversubscribed_group(category, users=10, quantity=1, capacity=10)
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    decisions = []
    for uid, _, _ in members:
        private = _private_allocation(uid)
        accepted = _accept(uid, private, allocation_set_hash)
        assert accepted.status_code == 200, accepted.text
        decisions.append((uid, private, accepted.json()))
    ready = client.post("/v1/collective-settlement/assess", json={"offer_id": offer["offer_id"]})
    assert ready.status_code == 200, ready.text
    assert ready.json()["settlement_ready"] is True
    uid, private, decision = decisions[0]
    issued = client.post(
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
    assert issued.status_code == 200, issued.text
    permit = issued.json()
    consumed = client.post(
        "/v1/settlement-permits/consume",
        json={
            "token": permit["proof"]["token"],
            "audience": permit["proof"]["claims"]["aud"],
            "request_id": f"prepare-settlement-{category}-0001",
        },
    )
    assert consumed.status_code == 200, consumed.text
    return uid, private, decision, permit


def _store(uid: str, claim_type: str, value: str):
    response = client.put(
        f"/v1/vault/users/{uid}/claims/{claim_type}",
        json={"value": value, "confirm": f"STORE VAULT CLAIM {claim_type}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _issue_disclosure(uid: str, permit_id: str, claim_types: list[str]):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        rows = (
            db.query(UserVaultClaim)
            .filter(UserVaultClaim.user_id == user.id, UserVaultClaim.claim_type.in_(claim_types))
            .all()
        )
        claim_hash = _claim_set_hash(rows)
    finally:
        db.close()
    response = client.post(
        f"/v1/vault/users/{uid}/disclosures",
        json={
            "settlement_permit_id": permit_id,
            "claim_types": claim_types,
            "expires_in_seconds": 600,
            "confirm": f"ISSUE DISCLOSURE {permit_id} {claim_hash[-12:]}",
        },
    )
    return response


def test_vault_encrypts_values_and_refuses_payment_or_arbitrary_self_claims():
    uid, _, _, _ = _prepared_user("vault-encryption")
    _store(uid, "delivery_name", "Ada Example")
    _store(uid, "address_line1", "10 Test Street")
    _store(uid, "city", "Paris")
    _store(uid, "country", "fr")
    _store(uid, "email", "ada@example.test")

    metadata = client.get(f"/v1/vault/users/{uid}/claims")
    assert metadata.status_code == 200
    body = metadata.json()
    assert body["raw_values_included"] is False
    assert body["payment_claims_allowed"] is False
    serialized = str(body)
    assert "10 Test Street" not in serialized
    assert "ada@example.test" not in serialized

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        address = db.query(UserVaultClaim).filter(
            UserVaultClaim.user_id == user.id,
            UserVaultClaim.claim_type == "address_line1",
        ).one()
        assert address.encrypted_value != "10 Test Street"
        assert "10 Test Street" not in address.encrypted_value
        assert address.value_fingerprint.startswith("sha256:")
    finally:
        db.close()

    forbidden = client.put(
        f"/v1/vault/users/{uid}/claims/card_number",
        json={"value": "4111111111111111", "confirm": "STORE VAULT CLAIM card_number"},
    )
    assert forbidden.status_code == 400
    arbitrary = client.put(
        f"/v1/vault/users/{uid}/claims/monthly_income",
        json={"value": "2200", "confirm": "STORE VAULT CLAIM monthly_income"},
    )
    assert arbitrary.status_code == 400


def test_selective_disclosure_proof_contains_no_values_and_consumes_exact_subset_once():
    uid, _, _, permit = _prepared_user("vault-minimal-disclosure")
    values = {
        "delivery_name": "Ada Example",
        "address_line1": "10 Test Street",
        "city": "Paris",
        "country": "FR",
        "email": "ada@example.test",
    }
    for claim_type, value in values.items():
        _store(uid, claim_type, value)

    requested = ["delivery_name", "city", "country"]
    issued = _issue_disclosure(uid, permit["permit"]["permit_id"], requested)
    assert issued.status_code == 200, issued.text
    body = issued.json()
    proof = body["proof"]
    assert proof["claims"]["claims"]["types"] == sorted(requested)
    assert proof["claims"]["capability"] == "reveal_fulfillment_claims"
    assert body["raw_values_in_proof"] is False
    assert body["payment_claims_allowed"] is False
    serialized = str(proof)
    for value in values.values():
        assert value not in serialized

    verified = client.post(
        "/v1/vault/disclosures/verify",
        json={"token": proof["token"], "audience": proof["claims"]["aud"]},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["raw_values_in_proof"] is False

    consumed = client.post(
        "/v1/vault/disclosures/consume",
        json={
            "token": proof["token"],
            "audience": proof["claims"]["aud"],
            "request_id": "fulfillment-disclosure-request-0001",
        },
    )
    assert consumed.status_code == 200, consumed.text
    disclosed = consumed.json()["disclosed_claims"]
    assert disclosed == {
        "delivery_name": "Ada Example",
        "city": "Paris",
        "country": "FR",
    }
    assert "address_line1" not in disclosed
    assert "email" not in disclosed
    assert consumed.json()["external_dispatch"] is False
    assert consumed.json()["payment_created"] is False
    assert consumed.json()["order_created"] is False

    second = client.post(
        "/v1/vault/disclosures/consume",
        json={
            "token": proof["token"],
            "audience": proof["claims"]["aud"],
            "request_id": "fulfillment-disclosure-request-0002",
        },
    )
    assert second.status_code == 400


def test_changing_authorized_claim_after_issuance_invalidates_grant_before_reveal():
    uid, _, _, permit = _prepared_user("vault-change-invalidates")
    _store(uid, "delivery_name", "Ada Example")
    _store(uid, "city", "Paris")
    _store(uid, "country", "FR")

    issued = _issue_disclosure(
        uid,
        permit["permit"]["permit_id"],
        ["delivery_name", "city", "country"],
    )
    assert issued.status_code == 200, issued.text
    proof = issued.json()["proof"]

    _store(uid, "city", "Lyon")
    verify = client.post(
        "/v1/vault/disclosures/verify",
        json={"token": proof["token"], "audience": proof["claims"]["aud"]},
    )
    assert verify.status_code == 400
    assert "claims changed" in verify.text.lower()

    consume = client.post(
        "/v1/vault/disclosures/consume",
        json={
            "token": proof["token"],
            "audience": proof["claims"]["aud"],
            "request_id": "fulfillment-disclosure-stale-0001",
        },
    )
    assert consume.status_code == 400


def test_disclosure_requires_consumed_settlement_permit():
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    members, offer, _ = _prepared_oversubscribed_group(
        "vault-parent-permit-required", users=10, quantity=1, capacity=10
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
    issued_permit = client.post(
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
    assert issued_permit.status_code == 200
    permit_id = issued_permit.json()["permit"]["permit_id"]
    _store(uid, "city", "Paris")
    blocked = _issue_disclosure(uid, permit_id, ["city"])
    assert blocked.status_code == 400
    assert "must be consumed" in blocked.text.lower()
