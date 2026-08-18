from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.allocation_models import CollectivePrivateAllocation
from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import User
from app.services.settlement_permit import SettlementPermitService
from app.settlement_permit_models import PseudonymousSettlementPermit, SettlementPermitUse
from app.settlement_permit_schemas import SettlementPermitConsume, SettlementPermitIssue
from tests.test_post_allocation_acceptance import _accept, _private_allocation
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group

client = TestClient(app)


def _ready_group(category: str, *, accept_count: int = 10):
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    members, offer, _ = _prepared_oversubscribed_group(
        category,
        users=10,
        quantity=1,
        capacity=10,
    )
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    accepted = []
    for uid, _, _ in members[:accept_count]:
        private = _private_allocation(uid)
        response = _accept(uid, private, allocation_set_hash)
        assert response.status_code == 200, response.text
        accepted.append((uid, private, response.json()))
    assessed = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert assessed.status_code == 200, assessed.text
    return members, offer, allocation, accepted, assessed.json()


def _issue(uid: str, allocation_entry_id: str, decision_hash: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        request = SettlementPermitIssue(
            allocation_entry_id=allocation_entry_id,
            expires_in_seconds=900,
            confirm=(
                f"ISSUE SETTLEMENT PERMIT {allocation_entry_id} "
                f"{decision_hash[-12:]}"
            ),
        )
        permit, proof = SettlementPermitService(db).issue(user, request)
        return permit.permit_id, proof
    finally:
        db.close()


def test_settlement_permit_requires_collective_readiness_and_is_minimal_pseudonymous():
    members, offer, _, accepted, settlement = _ready_group(
        "permit-minimal-pseudonymous",
        accept_count=10,
    )
    assert settlement["settlement_ready"] is True
    uid, private, decision = accepted[0]
    permit_id, proof = _issue(uid, private["allocation_entry_id"], decision["decision_hash"])

    claims = proof["claims"]
    assert claims["protocol"] == "hae-pseudonymous-settlement-permit-v1"
    assert claims["capability"] == "prepare_settlement"
    assert claims["aud"].startswith("responder:sha256:")
    assert claims["allocation"]["quantity"] == 1
    assert claims["terms"] == {
        "unit_price": 70.0,
        "currency": "EUR",
        "exact_total_amount": 70.0,
    }
    assert claims["max_uses"] == 1
    assert claims["sub"] != uid
    serialized = str(proof).lower()
    for forbidden in (
        uid.lower(),
        "monthly_income",
        "liquid_cash",
        "address",
        "email",
        "phone",
        "iban",
        "card_number",
        "payment_method",
    ):
        assert forbidden not in serialized

    db = SessionLocal()
    try:
        permit = db.query(PseudonymousSettlementPermit).filter(PseudonymousSettlementPermit.permit_id == permit_id).one()
        assert permit.token_hash.startswith("sha256:")
        assert proof["token"] not in permit.token_hash
        assert permit.status == "active"
        assert permit.use_count == 0
    finally:
        db.close()

    columns = {column["name"] for column in inspect(engine).get_columns("pseudonymous_settlement_permits")}
    assert "token" not in columns
    assert "token_hash" in columns
    assert "address" not in columns
    assert "email" not in columns
    assert "payment_method" not in columns


def test_public_cryptographic_verification_is_audience_bound_and_consumption_is_one_time():
    _, _, _, accepted, _ = _ready_group("permit-one-time", accept_count=10)
    uid, private, decision = accepted[0]
    permit_id, proof = _issue(uid, private["allocation_entry_id"], decision["decision_hash"])
    token = proof["token"]
    audience = proof["claims"]["aud"]

    db = SessionLocal()
    try:
        verified = SettlementPermitService(db).verify(token, audience)
        assert verified["valid"] is True
        assert verified["identity_disclosed"] is False
        assert verified["address_disclosed"] is False
        assert verified["payment_instrument_disclosed"] is False
        assert verified["external_dispatch"] is False
        assert verified["payment_created"] is False
        assert verified["order_created"] is False
    finally:
        db.close()

    db = SessionLocal()
    try:
        try:
            SettlementPermitService(db).verify(token, "responder:sha256:" + "0" * 64)
            assert False, "wrong audience must fail"
        except ValueError as exc:
            assert "audience" in str(exc).lower()
    finally:
        db.close()

    db = SessionLocal()
    try:
        use = SettlementPermitService(db).consume(
            SettlementPermitConsume(
                token=token,
                audience=audience,
                request_id="permit-consume-request-0001",
            )
        )
        assert use.request_id == "permit-consume-request-0001"
    finally:
        db.close()

    db = SessionLocal()
    try:
        permit = db.query(PseudonymousSettlementPermit).filter(PseudonymousSettlementPermit.permit_id == permit_id).one()
        assert permit.status == "consumed"
        assert permit.use_count == 1
        assert permit.consumed_at is not None
        assert db.query(SettlementPermitUse).filter(SettlementPermitUse.permit_db_id == permit.id).count() == 1
        try:
            SettlementPermitService(db).verify(token, audience)
            assert False, "consumed permit must no longer verify as active"
        except ValueError as exc:
            assert "not active" in str(exc).lower() or "exhausted" in str(exc).lower()
    finally:
        db.close()

    db = SessionLocal()
    try:
        try:
            SettlementPermitService(db).consume(
                SettlementPermitConsume(
                    token=token,
                    audience=audience,
                    request_id="permit-consume-request-0002",
                )
            )
            assert False, "second consume must fail"
        except ValueError as exc:
            assert "not active" in str(exc).lower() or "exhausted" in str(exc).lower()
    finally:
        db.close()


def test_nine_acceptances_cannot_issue_even_for_a_user_who_individually_accepted():
    _, _, _, accepted, settlement = _ready_group(
        "permit-blocked-below-settlement-threshold",
        accept_count=9,
    )
    assert settlement["published"] is False
    assert settlement["settlement_ready"] is False
    uid, private, decision = accepted[0]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        request = SettlementPermitIssue(
            allocation_entry_id=private["allocation_entry_id"],
            expires_in_seconds=900,
            confirm=(
                f"ISSUE SETTLEMENT PERMIT {private['allocation_entry_id']} "
                f"{decision['decision_hash'][-12:]}"
            ),
        )
        try:
            SettlementPermitService(db).issue(user, request)
            assert False, "collective readiness below anonymity threshold must block permit"
        except ValueError as exc:
            assert "not currently ready" in str(exc).lower()
    finally:
        db.close()


def test_acceptance_revocation_invalidates_unconsumed_permit_before_expiry():
    _, _, _, accepted, _ = _ready_group("permit-acceptance-revocation", accept_count=10)
    uid, private, decision = accepted[0]
    _, proof = _issue(uid, private["allocation_entry_id"], decision["decision_hash"])
    token = proof["token"]
    audience = proof["claims"]["aud"]

    revoked = client.post(
        f"/v1/collective-acceptance/users/{uid}/decisions/{decision['decision_id']}/revoke",
        json={"confirm": f"REVOKE ALLOCATION ACCEPTANCE {decision['decision_id']}"},
    )
    assert revoked.status_code == 200

    db = SessionLocal()
    try:
        try:
            SettlementPermitService(db).verify(token, audience)
            assert False, "revoked acceptance must stale permit"
        except ValueError as exc:
            text = str(exc).lower()
            assert "acceptance" in text or "commitment" in text or "readiness" in text
    finally:
        db.close()


def test_personal_mandate_change_invalidates_permit_and_exact_acceptance_cannot_issue_twice():
    _, _, _, accepted, _ = _ready_group("permit-mandate-change", accept_count=10)
    uid, private, decision = accepted[0]
    _, proof = _issue(uid, private["allocation_entry_id"], decision["decision_hash"])
    token = proof["token"]
    audience = proof["claims"]["aud"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        duplicate = SettlementPermitIssue(
            allocation_entry_id=private["allocation_entry_id"],
            expires_in_seconds=900,
            confirm=(
                f"ISSUE SETTLEMENT PERMIT {private['allocation_entry_id']} "
                f"{decision['decision_hash'][-12:]}"
            ),
        )
        try:
            SettlementPermitService(db).issue(user, duplicate)
            assert False, "same exact acceptance must not mint multiple permits"
        except ValueError as exc:
            assert "already issued" in str(exc).lower()
    finally:
        db.close()

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Pause settlement preparation.",
            "principles": ["manual only"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200

    db = SessionLocal()
    try:
        try:
            SettlementPermitService(db).verify(token, audience)
            assert False, "mandate change must invalidate permit"
        except ValueError as exc:
            assert "mandate" in str(exc).lower() or "private intent" in str(exc).lower()
    finally:
        db.close()
