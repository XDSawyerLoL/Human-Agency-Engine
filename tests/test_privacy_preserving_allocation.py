from fastapi.testclient import TestClient

from app.main import app
from app.services.policy import sha256_dict
from tests.test_collective_intent_pool import _join
from tests.test_collective_offer_protocol import _open_window, _seller, _signed_offer
from tests.test_private_collective_quorum import _commit, _evaluate
from tests.test_private_intent_market import _setup

client = TestClient(app)


def _open_quantity(uid: str, candidate_id: int, category: str, quantity: int):
    response = client.post(
        f"/v1/market/users/{uid}/intents",
        json={
            "candidate_id": candidate_id,
            "request_type": "product",
            "disclosure": {
                "category": category,
                "budget_max": 250,
                "currency": "EUR",
                "country": "FR",
                "quantity": quantity,
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


def _prepared_oversubscribed_group(category: str, *, users: int = 10, quantity: int = 2, capacity: int = 15):
    members = []
    for index in range(users):
        uid = f"{category}-user-{index:02d}"
        candidate_id = _setup(uid)
        envelope = _open_quantity(uid, candidate_id, category, quantity)
        membership = _join(uid, envelope["envelope_id"])
        members.append((uid, envelope, membership))

    if users < 10:
        return members, None, None

    window = _open_window(members[0][2]["cohort_key"])
    private, public_b64 = _seller()
    signed = _signed_offer(
        window["window_id"],
        private,
        public_b64,
        offer_id=f"{category}-offer",
        unit_price=70,
        minimum_collective_quantity=min(10, capacity),
        maximum_collective_quantity=capacity,
    )
    accepted = client.post(
        f"/v1/collective-market/windows/{window['window_id']}/offers",
        json=signed,
    )
    assert accepted.status_code == 200, accepted.text
    offer = accepted.json()
    commitments = []
    for uid, _, membership in members:
        evaluation = _evaluate(uid, membership["membership_id"], offer["offer_id"])
        assert evaluation["provisional_eligible"] is True
        committed = _commit(uid, membership["membership_id"], offer)
        assert committed.status_code == 200, committed.text
        commitments.append(committed.json())
    return members, offer, commitments


def _allocate(offer_id: str):
    quorum = client.get(f"/v1/collective-quorum/offers/{offer_id}")
    assert quorum.status_code == 200
    body = quorum.json()
    assert body["published"] is True
    commitment_set_hash = body["commitment_set_hash"]
    response = client.post(
        "/v1/collective-allocation",
        json={
            "offer_id": offer_id,
            "confirm": f"ALLOCATE COLLECTIVE OFFER {offer_id} {commitment_set_hash[-12:]}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_round_robin_allocation_gives_everyone_one_before_anyone_gets_two():
    category = "allocation-fair-round-robin"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=2, capacity=15)
    public = _allocate(offer["offer_id"])

    assert public["allocation_current"] is True
    summary = public["allocation"]
    assert summary["algorithm_version"] == "hae-fair-round-robin-v1"
    assert summary["committed_user_count"] == 10
    assert summary["committed_quantity"] == 20
    assert summary["capacity_quantity"] == 15
    assert summary["allocated_user_count"] == 10
    assert summary["allocated_quantity"] == 15
    assert summary["oversubscribed"] is True
    assert public["member_identities_included"] is False
    assert public["private_allocations_included"] is False
    assert public["payment_created"] is False
    assert public["order_created"] is False

    allocations = []
    for uid, _, _ in members:
        own = client.get(f"/v1/collective-allocation/users/{uid}")
        assert own.status_code == 200
        assert len(own.json()["allocations"]) == 1
        item = own.json()["allocations"][0]
        allocations.append(item)
        assert item["requested_quantity"] == 2
        assert item["allocated_quantity"] in {1, 2}
        assert item["shared_with_responder"] is False
        assert item["payment_created"] is False
        assert item["order_created"] is False
        assert item["priority_hash"] == sha256_dict(
            {"seed_hash": item["seed_hash"], "conditions_hash": item["conditions_hash"]}
        )

    quantities = sorted(item["allocated_quantity"] for item in allocations)
    assert quantities == [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
    assert sum(quantities) == 15

    serialized_public = str(public)
    for uid, _, membership in members:
        assert uid not in serialized_public
        assert membership["membership_id"] not in serialized_public
    for item in allocations:
        assert item["allocation_entry_id"] not in serialized_public
        assert item["conditions_hash"] not in serialized_public
        assert item["priority_hash"] not in serialized_public


def test_allocation_is_idempotent_for_same_exact_commitment_set():
    category = "allocation-idempotent"
    _, offer, _ = _prepared_oversubscribed_group(category, quantity=2, capacity=15)
    first = _allocate(offer["offer_id"])
    second = _allocate(offer["offer_id"])
    assert first["allocation"]["allocation_id"] == second["allocation"]["allocation_id"]
    assert first["allocation"]["seed_hash"] == second["allocation"]["seed_hash"]
    assert first["allocation"]["allocation_set_hash"] == second["allocation"]["allocation_set_hash"]


def test_revoked_commitment_invalidates_old_public_allocation_instead_of_exposing_history():
    category = "allocation-revocation-stale"
    members, offer, commitments = _prepared_oversubscribed_group(category, quantity=2, capacity=15)
    allocated = _allocate(offer["offer_id"])
    assert allocated["allocation_current"] is True

    uid = members[-1][0]
    commitment = commitments[-1]
    revoked = client.post(
        f"/v1/collective-quorum/users/{uid}/commitments/{commitment['commitment_id']}/revoke",
        json={"confirm": f"REVOKE CONDITIONAL COMMITMENT {commitment['commitment_id']}"},
    )
    assert revoked.status_code == 200

    current = client.get(f"/v1/collective-allocation/offers/{offer['offer_id']}")
    assert current.status_code == 200
    body = current.json()
    assert body["allocation_current"] is False
    assert body["allocation"] is None
    assert body["member_identities_included"] is False
    assert body["private_allocations_included"] is False


def test_allocation_cannot_run_below_commitment_privacy_threshold():
    # The cohort itself must have 10 users to open a collective offer, so create a
    # full cohort but conditionally commit only nine of them.
    category = "allocation-below-commitment-threshold"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=1, capacity=100)

    # Revoke the tenth existing commitment before any allocation.
    tenth_uid = members[-1][0]
    own = client.get(f"/v1/collective-quorum/users/{tenth_uid}/commitments").json()["commitments"][0]
    revoked = client.post(
        f"/v1/collective-quorum/users/{tenth_uid}/commitments/{own['commitment_id']}/revoke",
        json={"confirm": f"REVOKE CONDITIONAL COMMITMENT {own['commitment_id']}"},
    )
    assert revoked.status_code == 200

    response = client.post(
        "/v1/collective-allocation",
        json={
            "offer_id": offer["offer_id"],
            "confirm": f"ALLOCATE COLLECTIVE OFFER {offer['offer_id']} {'0' * 12}",
        },
    )
    assert response.status_code == 400
    assert "below privacy threshold" in response.text.lower()
