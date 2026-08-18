import base64
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.collective_offer_models import CollectiveMarketWindow
from app.collective_offer_schemas import CollectiveOfferSubmit
from app.db import SessionLocal
from app.main import app
from app.services.collective_offers import collective_offer_signed_payload
from app.services.policy import canonical_json
from tests.test_collective_intent_pool import _join, _open_custom
from tests.test_private_intent_market import _setup

client = TestClient(app)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _cohort(category: str, *, budgets=None):
    members = []
    for index in range(10):
        uid = f"{category}-user-{index:02d}"
        candidate_id = _setup(uid)
        budget = budgets[index] if budgets is not None else 100
        envelope = _open_custom(uid, candidate_id, category, budget=budget)
        membership = _join(uid, envelope["envelope_id"])
        members.append((uid, envelope, membership))
    return members


def _open_window(cohort_key: str):
    response = client.post(
        "/v1/collective-market/windows",
        json={
            "cohort_key": cohort_key,
            "expires_in_seconds": 86400,
            "confirm": f"OPEN COLLECTIVE MARKET {cohort_key}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seller():
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, _b64u(public_raw)


def _signed_offer(window_id: str, private, public_b64: str, **overrides):
    payload = {
        "offer_id": uuid.uuid4().hex,
        "responder_label": "Collective Seller Agent",
        "public_key_b64": public_b64,
        "unit_price": 70,
        "currency": "EUR",
        "minimum_collective_quantity": 8,
        "maximum_collective_quantity": 100,
        "delivery_days": 3,
        "return_window_days": 30,
        "cancellation_allowed": True,
        "available": True,
        "features": ["wide fit", "breathable"],
        "condition": "new",
        "commission_per_unit": 0,
        "commission_currency": "EUR",
        "valid_until_epoch": int(time.time()) + 3600,
        "signature_b64": "x" * 64,
    }
    payload.update(overrides)
    db = SessionLocal()
    try:
        window = db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.window_id == window_id).one()
        request = CollectiveOfferSubmit(**payload)
        signed = collective_offer_signed_payload(window, request)
    finally:
        db.close()
    payload["signature_b64"] = _b64u(private.sign(canonical_json(signed)))
    return payload


def test_collective_window_freezes_only_public_thresholded_snapshot():
    category = "collective-offer-window-private"
    members = _cohort(category)
    cohort_key = members[0][2]["cohort_key"]
    window = _open_window(cohort_key)

    assert window["protocol"] == "hae-collective-offer-v1"
    assert window["snapshot"]["cohort_size"] == 10
    assert window["snapshot"]["descriptor"]["category"] == category
    assert window["source_set_hash"] == window["snapshot"]["aggregate"]["source_set_hash"]
    assert window["aggregate_hash"].startswith("sha256:")
    assert window["privacy"] == {
        "member_identities_included": False,
        "membership_ids_included": False,
        "envelope_ids_included": False,
        "subject_refs_included": False,
        "individual_budgets_included": False,
        "individual_evaluations_included": False,
    }

    serialized = str(window)
    for uid, envelope, membership in members:
        assert uid not in serialized
        assert envelope["envelope_id"] not in serialized
        assert envelope["subject_ref"] not in serialized
        assert membership["membership_id"] not in serialized


def test_signed_collective_offer_is_bound_to_exact_window_and_demand_is_not_commitment():
    category = "collective-offer-signature"
    members = _cohort(category)
    window = _open_window(members[0][2]["cohort_key"])
    private, public_b64 = _seller()
    offer = _signed_offer(window["window_id"], private, public_b64, offer_id="collective-signed-offer-1")

    accepted = client.post(
        f"/v1/collective-market/windows/{window['window_id']}/offers",
        json=offer,
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["identity_assurance"] == "key_possession_only"
    assert body["group_eligibility"]["eligible"] is True
    assert body["group_eligibility"]["demand_pool_quantity"] == 10
    assert body["group_eligibility"]["demand_is_not_commitment"] is True
    assert body["group_eligibility"]["commission_considered"] is False
    assert body["individual_evaluations_included"] is False
    assert body["member_identities_included"] is False

    attacker = Ed25519PrivateKey.generate()
    tampered = _signed_offer(window["window_id"], private, public_b64, offer_id="collective-signed-offer-2")
    db = SessionLocal()
    try:
        window_row = db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.window_id == window["window_id"]).one()
        signed = collective_offer_signed_payload(window_row, CollectiveOfferSubmit(**tampered))
    finally:
        db.close()
    tampered["signature_b64"] = _b64u(attacker.sign(canonical_json(signed)))
    rejected = client.post(
        f"/v1/collective-market/windows/{window['window_id']}/offers",
        json=tampered,
    )
    assert rejected.status_code == 400
    assert "signed collective market offer" in rejected.text.lower()


def test_private_agents_can_reach_different_results_without_leaking_evaluations_to_seller_view():
    category = "collective-offer-private-evaluation"
    budgets = [60, 100] + [100] * 8
    members = _cohort(category, budgets=budgets)
    window = _open_window(members[0][2]["cohort_key"])
    private, public_b64 = _seller()
    offer = _signed_offer(window["window_id"], private, public_b64, offer_id="collective-private-fit-offer")
    accepted = client.post(f"/v1/collective-market/windows/{window['window_id']}/offers", json=offer)
    assert accepted.status_code == 200

    uid_low, _, membership_low = members[0]
    low = client.post(
        f"/v1/collective-market/users/{uid_low}/evaluate",
        json={"membership_id": membership_low["membership_id"], "offer_id": "collective-private-fit-offer"},
    )
    assert low.status_code == 200, low.text
    assert low.json()["provisional_eligible"] is False
    assert any("budget" in reason.lower() for reason in low.json()["reasons"])
    assert low.json()["shared_with_responder"] is False

    uid_ok, _, membership_ok = members[1]
    ok = client.post(
        f"/v1/collective-market/users/{uid_ok}/evaluate",
        json={"membership_id": membership_ok["membership_id"], "offer_id": "collective-private-fit-offer"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["provisional_eligible"] is True
    assert ok.json()["fiduciary_score"] is not None
    assert ok.json()["collective_minimum_not_committed"] is True
    assert ok.json()["shared_with_responder"] is False

    merchant_view = client.get(f"/v1/collective-market/windows/{window['window_id']}/offers")
    assert merchant_view.status_code == 200
    serialized = str(merchant_view.json())
    assert low.json()["evaluation_id"] not in serialized
    assert ok.json()["evaluation_id"] not in serialized
    assert uid_low not in serialized
    assert uid_ok not in serialized
    assert merchant_view.json()["individual_evaluations_included"] is False


def test_collective_commission_is_excluded_from_private_fiduciary_score():
    category = "collective-offer-commission"
    members = _cohort(category)
    window = _open_window(members[0][2]["cohort_key"])
    private_a, public_a = _seller()
    private_b, public_b = _seller()
    zero = _signed_offer(
        window["window_id"],
        private_a,
        public_a,
        offer_id="collective-commission-zero",
        commission_per_unit=0,
    )
    huge = _signed_offer(
        window["window_id"],
        private_b,
        public_b,
        offer_id="collective-commission-huge",
        commission_per_unit=500,
    )
    assert client.post(f"/v1/collective-market/windows/{window['window_id']}/offers", json=zero).status_code == 200
    assert client.post(f"/v1/collective-market/windows/{window['window_id']}/offers", json=huge).status_code == 200

    uid, _, membership = members[0]
    first = client.post(
        f"/v1/collective-market/users/{uid}/evaluate",
        json={"membership_id": membership["membership_id"], "offer_id": "collective-commission-zero"},
    )
    second = client.post(
        f"/v1/collective-market/users/{uid}/evaluate",
        json={"membership_id": membership["membership_id"], "offer_id": "collective-commission-huge"},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["fiduciary_score"] == second.json()["fiduciary_score"]
    assert first.json()["score_components"] == second.json()["score_components"]
    assert first.json()["commission_excluded_from_ranking"] is True
    assert second.json()["commission_excluded_from_ranking"] is True


def test_window_becomes_stale_when_cohort_composition_changes_even_above_threshold():
    category = "collective-offer-stale-snapshot"
    members = _cohort(category)
    window = _open_window(members[0][2]["cohort_key"])

    new_uid = f"{category}-user-10"
    candidate_id = _setup(new_uid)
    new_envelope = _open_custom(new_uid, candidate_id, category)
    _join(new_uid, new_envelope["envelope_id"])

    private, public_b64 = _seller()
    offer = _signed_offer(window["window_id"], private, public_b64, offer_id="collective-stale-window-offer")
    rejected = client.post(
        f"/v1/collective-market/windows/{window['window_id']}/offers",
        json=offer,
    )
    assert rejected.status_code == 400
    assert "composition changed" in rejected.text.lower()
