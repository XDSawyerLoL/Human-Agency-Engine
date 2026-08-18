import base64
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.market_models import MarketOffer, PrivateIntentEnvelope
from app.market_schemas import MarketOfferSubmit
from app.models import User
from app.services.market import market_offer_signed_payload
from app.services.policy import canonical_json
from app.synthesis_models import CandidateIntervention

client = TestClient(app)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _setup(uid: str) -> int:
    user_response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2200,
            "monthly_fixed_costs": 1300,
            "liquid_cash": 900,
            "minimum_cash_buffer": 200,
        },
    )
    assert user_response.status_code == 200
    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Let the market compete for me without exposing my private model.",
            "principles": ["privacy", "fiduciary ranking"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert mandate.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        candidate = CandidateIntervention(
            user_id=user.id,
            candidate_key=uuid.uuid4().hex,
            source_type="test",
            source_ref="private-intent-market-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Find a suitable product without exposing private context",
            rationale="Synthetic reviewed candidate for market protocol tests.",
            intervention={"type": "request_market_offers", "reversible": True},
            effects={},
            assumptions=[],
            evidence={"level": "personal_repeated", "sources": ["test"]},
            confidence=0.8,
            status="ready_for_review",
            decision_status="candidate_for_reversible_pilot",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate.id
    finally:
        db.close()


def _open(uid: str, candidate_id: int):
    response = client.post(
        f"/v1/market/users/{uid}/intents",
        json={
            "candidate_id": candidate_id,
            "request_type": "product",
            "disclosure": {
                "category": "walking shoes",
                "budget_max": 100,
                "currency": "EUR",
                "country": "FR",
                "quantity": 1,
                "size": "44",
                "required_features": ["wide fit", "breathable"],
                "desired_within_days": 5,
                "condition": "new",
            },
            "ranking_policy": {
                "price_weight": 0.5,
                "delivery_weight": 0.2,
                "reversibility_weight": 0.3,
            },
            "expires_in_seconds": 86400,
            "confirm": f"OPEN MARKET INTENT {candidate_id}",
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


def _signed_offer(envelope_id: str, private, public_b64: str, **overrides):
    payload = {
        "offer_id": uuid.uuid4().hex,
        "responder_label": "Seller Agent",
        "public_key_b64": public_b64,
        "price_total": 70,
        "currency": "EUR",
        "delivery_days": 3,
        "return_window_days": 30,
        "cancellation_allowed": True,
        "available": True,
        "quantity_available": 10,
        "features": ["wide fit", "breathable"],
        "condition": "new",
        "commission_amount": 0,
        "commission_currency": "EUR",
        "signature_b64": "x" * 64,
    }
    payload.update(overrides)

    db = SessionLocal()
    try:
        envelope = db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.envelope_id == envelope_id).one()
        request = MarketOfferSubmit(**payload)
        signed = market_offer_signed_payload(envelope, request)
    finally:
        db.close()
    payload["signature_b64"] = _b64u(private.sign(canonical_json(signed)))
    return payload


def test_private_envelope_exposes_only_explicit_structured_disclosure():
    uid = "market-privacy-a"
    candidate_id = _setup(uid)
    envelope = _open(uid, candidate_id)

    assert envelope["protocol"] == "hae-private-intent-market-v1"
    assert envelope["privacy"] == {
        "self_graph_included": False,
        "raw_intent_included": False,
        "identity_included": False,
        "exact_address_included": False,
        "income_included": False,
        "emotional_state_included": False,
    }
    serialized = str(envelope).lower()
    for forbidden in (
        "monthly_income",
        "monthly_fixed_costs",
        "liquid_cash",
        "minimum_cash_buffer",
        "mission",
        "external_id",
        uid.lower(),
    ):
        assert forbidden not in serialized
    assert envelope["disclosure"]["category"] == "walking shoes"
    assert envelope["disclosure"]["budget_max"] == 100
    assert envelope["disclosure"]["country"] == "FR"
    assert envelope["subject_ref"] != uid


def test_signed_offer_requires_responder_key_possession_and_challenge_binding():
    uid = "market-signature-b"
    candidate_id = _setup(uid)
    envelope = _open(uid, candidate_id)
    private, public_b64 = _seller()
    offer = _signed_offer(envelope["envelope_id"], private, public_b64)

    accepted = client.post(
        f"/v1/market/intents/{envelope['envelope_id']}/offers",
        json=offer,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["identity_assurance"] == "key_possession_only"
    assert accepted.json()["eligibility"]["eligible"] is True

    attacker = Ed25519PrivateKey.generate()
    tampered_offer = _signed_offer(
        envelope["envelope_id"],
        private,
        public_b64,
        offer_id=uuid.uuid4().hex,
    )
    db = SessionLocal()
    try:
        envelope_row = db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.envelope_id == envelope["envelope_id"]).one()
        request = MarketOfferSubmit(**tampered_offer)
        signed = market_offer_signed_payload(envelope_row, request)
    finally:
        db.close()
    tampered_offer["signature_b64"] = _b64u(attacker.sign(canonical_json(signed)))
    rejected = client.post(
        f"/v1/market/intents/{envelope['envelope_id']}/offers",
        json=tampered_offer,
    )
    assert rejected.status_code == 400
    assert "signed market offer" in rejected.text.lower()


def test_commission_is_mathematically_excluded_from_fiduciary_ranking():
    uid = "market-ranking-c"
    candidate_id = _setup(uid)
    envelope = _open(uid, candidate_id)
    private_a, public_a = _seller()
    private_b, public_b = _seller()
    private_c, public_c = _seller()

    better = _signed_offer(
        envelope["envelope_id"],
        private_a,
        public_a,
        offer_id="offer-better-user-value",
        price_total=60,
        delivery_days=2,
        return_window_days=30,
        cancellation_allowed=True,
        commission_amount=0,
    )
    worse_high_commission = _signed_offer(
        envelope["envelope_id"],
        private_b,
        public_b,
        offer_id="offer-worse-high-commission",
        price_total=90,
        delivery_days=8,
        return_window_days=0,
        cancellation_allowed=False,
        commission_amount=40,
    )
    identical_high_commission = _signed_offer(
        envelope["envelope_id"],
        private_c,
        public_c,
        offer_id="offer-identical-high-commission",
        price_total=60,
        delivery_days=2,
        return_window_days=30,
        cancellation_allowed=True,
        commission_amount=500,
    )
    for offer in (better, worse_high_commission, identical_high_commission):
        response = client.post(
            f"/v1/market/intents/{envelope['envelope_id']}/offers",
            json=offer,
        )
        assert response.status_code == 200, response.text

    ranked = client.get(f"/v1/market/intents/{envelope['envelope_id']}/ranked")
    assert ranked.status_code == 200, ranked.text
    body = ranked.json()
    assert body["commission_excluded_from_ranking"] is True
    by_id = {item["offer_id"]: item for item in body["offers"]}
    assert by_id["offer-better-user-value"]["fiduciary_score"] > by_id["offer-worse-high-commission"]["fiduciary_score"]
    assert by_id["offer-better-user-value"]["fiduciary_score"] == by_id["offer-identical-high-commission"]["fiduciary_score"]
    assert by_id["offer-identical-high-commission"]["commission"]["amount"] == 500
    assert body["offers"][0]["offer_id"] in {"offer-better-user-value", "offer-identical-high-commission"}


def test_budget_and_required_features_gate_eligibility_without_using_commission():
    uid = "market-eligibility-d"
    candidate_id = _setup(uid)
    envelope = _open(uid, candidate_id)
    private, public_b64 = _seller()
    too_expensive = _signed_offer(
        envelope["envelope_id"],
        private,
        public_b64,
        offer_id="offer-over-budget",
        price_total=150,
        commission_amount=0,
    )
    missing_feature = _signed_offer(
        envelope["envelope_id"],
        private,
        public_b64,
        offer_id="offer-missing-feature",
        price_total=50,
        features=["wide fit"],
        commission_amount=0,
    )
    for offer in (too_expensive, missing_feature):
        response = client.post(
            f"/v1/market/intents/{envelope['envelope_id']}/offers",
            json=offer,
        )
        assert response.status_code == 200
        assert response.json()["eligibility"]["eligible"] is False
        assert response.json()["eligibility"]["commission_considered"] is False

    ranked = client.get(f"/v1/market/intents/{envelope['envelope_id']}/ranked").json()
    assert all(item["eligible"] is False for item in ranked["offers"])
    assert all(item["fiduciary_score"] is None for item in ranked["offers"])


def test_mandate_change_or_revocation_closes_market_path_and_user_delete_cascades():
    uid = "market-lifecycle-e"
    candidate_id = _setup(uid)
    envelope = _open(uid, candidate_id)
    private, public_b64 = _seller()

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Pause all market requests.",
            "principles": ["manual review"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200
    stale_offer = _signed_offer(envelope["envelope_id"], private, public_b64, offer_id="stale-offer")
    rejected = client.post(
        f"/v1/market/intents/{envelope['envelope_id']}/offers",
        json=stale_offer,
    )
    assert rejected.status_code == 400
    assert "mandate changed" in rejected.text.lower()

    uid2 = "market-lifecycle-f"
    candidate_id2 = _setup(uid2)
    envelope2 = _open(uid2, candidate_id2)
    private2, public2 = _seller()
    accepted_offer = _signed_offer(envelope2["envelope_id"], private2, public2, offer_id="offer-before-revoke")
    assert client.post(
        f"/v1/market/intents/{envelope2['envelope_id']}/offers",
        json=accepted_offer,
    ).status_code == 200

    revoked = client.post(
        f"/v1/market/users/{uid2}/intents/{envelope2['envelope_id']}/revoke",
        json={"confirm": f"REVOKE MARKET INTENT {envelope2['envelope_id']}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    late_offer = _signed_offer(envelope2["envelope_id"], private2, public2, offer_id="offer-after-revoke")
    assert client.post(
        f"/v1/market/intents/{envelope2['envelope_id']}/offers",
        json=late_offer,
    ).status_code == 400

    db = SessionLocal()
    try:
        user_id = db.query(User).filter(User.external_id == uid2).one().id
        assert db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.user_id == user_id).count() == 1
        assert db.query(MarketOffer).count() >= 1
    finally:
        db.close()

    deleted = client.delete(f"/v1/users/{uid2}", params={"confirm": f"DELETE {uid2}"})
    assert deleted.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.user_id == user_id).count() == 0
        assert db.query(MarketOffer).filter(MarketOffer.offer_id == "offer-before-revoke").count() == 0
    finally:
        db.close()
