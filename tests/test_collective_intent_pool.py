import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.synthesis_models import CandidateIntervention
from tests.test_private_intent_market import _setup

client = TestClient(app)


def _open_custom(uid: str, candidate_id: int, category: str, *, desired_days: int = 5, budget: float = 100):
    response = client.post(
        f"/v1/market/users/{uid}/intents",
        json={
            "candidate_id": candidate_id,
            "request_type": "product",
            "disclosure": {
                "category": category,
                "budget_max": budget,
                "currency": "EUR",
                "country": "FR",
                "quantity": 1,
                "size": "44",
                "required_features": ["wide fit", "breathable"],
                "desired_within_days": desired_days,
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


def _join(uid: str, envelope_id: str):
    response = client.post(
        f"/v1/collective/users/{uid}/join",
        json={
            "envelope_id": envelope_id,
            "confirm": f"JOIN COLLECTIVE INTENT {envelope_id}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _new_candidate_for_existing_user(uid: str) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        candidate = CandidateIntervention(
            user_id=user.id,
            candidate_key=uuid.uuid4().hex,
            source_type="test",
            source_ref="collective-second-envelope-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Second private market request",
            rationale="Synthetic second reviewed candidate for distinct-user aggregation testing.",
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


def _create_members(category: str, count: int, *, prefix: str, desired_days=None):
    members = []
    for index in range(count):
        uid = f"{prefix}-{index:02d}"
        candidate_id = _setup(uid)
        days = desired_days(index) if callable(desired_days) else (desired_days if desired_days is not None else 5)
        envelope = _open_custom(uid, candidate_id, category, desired_days=days)
        membership = _join(uid, envelope["envelope_id"])
        members.append((uid, candidate_id, envelope, membership))
    return members


def test_below_threshold_hides_count_descriptor_and_individual_references():
    category = "collective-private-below-threshold"
    uid = "collective-private-single"
    candidate_id = _setup(uid)
    envelope = _open_custom(uid, candidate_id, category)
    membership = _join(uid, envelope["envelope_id"])

    aggregate = client.get(f"/v1/collective/cohorts/{membership['cohort_key']}")
    assert aggregate.status_code == 200
    body = aggregate.json()
    assert body["published"] is False
    assert body["state"] == "below_privacy_threshold"
    assert body["cohort_size"] is None
    assert body["descriptor"] is None
    assert body["aggregate"] is None
    assert body["privacy"]["minimum_cohort_size"] == 10
    assert body["privacy"]["formal_differential_privacy"] is False

    serialized = str(body)
    assert uid not in serialized
    assert envelope["envelope_id"] not in serialized
    assert envelope["subject_ref"] not in serialized


def test_ten_distinct_users_publish_only_broad_aggregate_without_member_ids():
    category = "collective-threshold-ten"
    members = _create_members(category, 10, prefix="collective-ten")
    cohort_key = members[0][3]["cohort_key"]

    aggregate = client.get(f"/v1/collective/cohorts/{cohort_key}")
    assert aggregate.status_code == 200
    body = aggregate.json()
    assert body["published"] is True
    assert body["state"] == "privacy_threshold_met"
    assert body["cohort_size"] == 10
    assert body["descriptor"] == {
        "request_type": "product",
        "category": category,
        "currency": "EUR",
        "country": "FR",
    }
    assert body["aggregate"]["total_quantity"] == 10
    assert body["aggregate"]["median_budget_bucket"] == {
        "min": 100.0,
        "max_exclusive": 125.0,
        "currency": "EUR",
    }
    assert body["aggregate"]["delivery_preference_buckets"] == {"4_7_days": 10}
    assert body["aggregate"]["source_set_hash"].startswith("sha256:")

    privacy = body["privacy"]
    assert privacy["distinct_users_only"] is True
    assert privacy["user_ids_included"] is False
    assert privacy["envelope_ids_included"] is False
    assert privacy["subject_refs_included"] is False
    assert privacy["individual_contributions_included"] is False
    assert privacy["formal_differential_privacy"] is False

    serialized = str(body)
    for uid, _, envelope, membership in members:
        assert uid not in serialized
        assert envelope["envelope_id"] not in serialized
        assert envelope["subject_ref"] not in serialized
        assert membership["membership_id"] not in serialized


def test_same_user_replacing_envelope_does_not_increase_collective_headcount():
    category = "collective-distinct-user"
    members = _create_members(category, 10, prefix="collective-distinct")
    uid, _, first_envelope, first_membership = members[0]
    cohort_key = first_membership["cohort_key"]

    second_candidate = _new_candidate_for_existing_user(uid)
    second_envelope = _open_custom(uid, second_candidate, category, budget=75)
    second_membership = _join(uid, second_envelope["envelope_id"])
    assert second_membership["membership_id"] == first_membership["membership_id"]
    assert second_membership["envelope_id"] == second_envelope["envelope_id"]
    assert second_membership["envelope_id"] != first_envelope["envelope_id"]

    aggregate = client.get(f"/v1/collective/cohorts/{cohort_key}").json()
    assert aggregate["published"] is True
    assert aggregate["cohort_size"] == 10
    assert aggregate["aggregate"]["total_quantity"] == 10


def test_small_delivery_cells_are_suppressed_inside_published_cohort():
    category = "collective-small-cell-suppression"
    members = _create_members(
        category,
        10,
        prefix="collective-cell",
        desired_days=lambda index: 5 if index < 8 else 30,
    )
    cohort_key = members[0][3]["cohort_key"]
    body = client.get(f"/v1/collective/cohorts/{cohort_key}").json()
    assert body["published"] is True
    buckets = body["aggregate"]["delivery_preference_buckets"]
    assert buckets["4_7_days"] == 8
    assert buckets["suppressed"] == 2
    assert "15_30_days" not in buckets
    assert body["privacy"]["minimum_published_cell_size"] == 3


def test_leaving_tenth_member_immediately_rehides_collective_view():
    category = "collective-threshold-dynamic"
    members = _create_members(category, 10, prefix="collective-leave")
    cohort_key = members[0][3]["cohort_key"]
    before = client.get(f"/v1/collective/cohorts/{cohort_key}").json()
    assert before["published"] is True
    assert before["cohort_size"] == 10

    uid, _, _, membership = members[-1]
    left = client.post(
        f"/v1/collective/users/{uid}/memberships/{membership['membership_id']}/leave",
        json={"confirm": f"LEAVE COLLECTIVE INTENT {membership['membership_id']}"},
    )
    assert left.status_code == 200
    assert left.json()["status"] == "left"

    after = client.get(f"/v1/collective/cohorts/{cohort_key}").json()
    assert after["published"] is False
    assert after["state"] == "below_privacy_threshold"
    assert after["cohort_size"] is None
    assert after["descriptor"] is None
    assert after["aggregate"] is None
