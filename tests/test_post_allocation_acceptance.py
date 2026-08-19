from fastapi.testclient import TestClient

from app.main import app
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group

client = TestClient(app)


def _private_allocation(uid: str):
    response = client.get(f"/v1/collective-allocation/users/{uid}")
    assert response.status_code == 200
    assert len(response.json()["allocations"]) == 1
    return response.json()["allocations"][0]


def _accept(uid: str, private: dict, allocation_set_hash: str):
    return client.post(
        f"/v1/collective-acceptance/users/{uid}/accept",
        json={
            "allocation_entry_id": private["allocation_entry_id"],
            "confirm": (
                f"ACCEPT ALLOCATION {private['allocation_entry_id']} "
                f"{private['allocated_quantity']} {allocation_set_hash[-12:]}"
            ),
        },
    )


def _reject(uid: str, private: dict, allocation_set_hash: str):
    return client.post(
        f"/v1/collective-acceptance/users/{uid}/reject",
        json={
            "allocation_entry_id": private["allocation_entry_id"],
            "confirm": (
                f"REJECT ALLOCATION {private['allocation_entry_id']} "
                f"{private['allocated_quantity']} {allocation_set_hash[-12:]}"
            ),
        },
    )


def test_user_explicitly_accepts_exact_allocated_quantity_and_terms_only():
    category = "acceptance-exact-terms"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=2, capacity=15)
    public = _allocate(offer["offer_id"])
    allocation_set_hash = public["allocation"]["allocation_set_hash"]
    uid = members[0][0]
    private = _private_allocation(uid)
    assert private["allocated_quantity"] in {1, 2}

    accepted = _accept(uid, private, allocation_set_hash)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["decision"] == "accepted"
    assert body["effective_acceptance"] is True
    assert body["allocated_quantity"] == private["allocated_quantity"]
    assert body["unit_price"] == 70.0
    assert body["currency"] == "EUR"
    assert body["exact_total_amount"] == 70.0 * private["allocated_quantity"]
    assert body["allocation_set_hash"] == allocation_set_hash
    assert body["offer_hash"]
    assert body["conditions_hash"] == private["conditions_hash"]
    assert body["shared_with_responder"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False

    repeated = _accept(uid, private, allocation_set_hash)
    assert repeated.status_code == 200
    assert repeated.json()["decision_id"] == body["decision_id"]

    merchant_safe = client.get(f"/v1/collective-allocation/offers/{offer['offer_id']}")
    assert merchant_safe.status_code == 200
    serialized = str(merchant_safe.json())
    assert uid not in serialized
    assert body["decision_id"] not in serialized
    assert body["decision_hash"] not in serialized


def test_waitlisted_zero_allocation_cannot_be_accepted_as_if_it_were_an_order():
    category = "acceptance-waitlist-zero"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=1, capacity=5)
    public = _allocate(offer["offer_id"])
    allocation_set_hash = public["allocation"]["allocation_set_hash"]

    waitlisted = None
    waitlisted_uid = None
    for uid, _, _ in members:
        private = _private_allocation(uid)
        if private["status"] == "waitlisted":
            waitlisted = private
            waitlisted_uid = uid
            break
    assert waitlisted is not None
    assert waitlisted["allocated_quantity"] == 0

    response = _accept(waitlisted_uid, waitlisted, allocation_set_hash)
    assert response.status_code == 400
    assert "positive allocated quantity" in response.text.lower()

    own = client.get(f"/v1/collective-acceptance/users/{waitlisted_uid}")
    assert own.status_code == 200
    assert own.json()["decisions"] == []
    assert own.json()["shared_with_responders"] is False


def test_rejecting_an_allocation_revokes_underlying_commitment_and_invalidates_round():
    category = "acceptance-reject-invalidates"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=1, capacity=10)
    public = _allocate(offer["offer_id"])
    allocation_set_hash = public["allocation"]["allocation_set_hash"]
    uid = members[0][0]
    private = _private_allocation(uid)
    assert private["allocated_quantity"] == 1

    rejected = _reject(uid, private, allocation_set_hash)
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["decision"] == "rejected"
    assert body["effective_acceptance"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False

    current = client.get(f"/v1/collective-allocation/offers/{offer['offer_id']}")
    assert current.status_code == 200
    assert current.json()["allocation_current"] is False
    assert current.json()["allocation"] is None


def test_revoking_acceptance_withdraws_commitment_and_makes_old_round_stale():
    category = "acceptance-revoke-invalidates"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=1, capacity=10)
    public = _allocate(offer["offer_id"])
    allocation_set_hash = public["allocation"]["allocation_set_hash"]
    uid = members[0][0]
    private = _private_allocation(uid)

    accepted = _accept(uid, private, allocation_set_hash)
    assert accepted.status_code == 200
    decision = accepted.json()
    revoked = client.post(
        f"/v1/collective-acceptance/users/{uid}/decisions/{decision['decision_id']}/revoke",
        json={"confirm": f"REVOKE ALLOCATION ACCEPTANCE {decision['decision_id']}"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["decision"] == "accepted"
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["effective_acceptance"] is False
    assert revoked.json()["payment_created"] is False
    assert revoked.json()["order_created"] is False

    current = client.get(f"/v1/collective-allocation/offers/{offer['offer_id']}")
    assert current.status_code == 200
    assert current.json()["allocation_current"] is False


def test_mandate_change_blocks_acceptance_before_any_transactional_state_exists():
    category = "acceptance-mandate-stale"
    members, offer, _ = _prepared_oversubscribed_group(category, quantity=1, capacity=10)
    public = _allocate(offer["offer_id"])
    allocation_set_hash = public["allocation"]["allocation_set_hash"]
    uid = members[0][0]
    private = _private_allocation(uid)

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Pause collective purchase-like actions.",
            "principles": ["manual only"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200

    accepted = _accept(uid, private, allocation_set_hash)
    assert accepted.status_code == 400
    assert "private intent envelope is no longer live" in accepted.text.lower()

    own = client.get(f"/v1/collective-acceptance/users/{uid}")
    assert own.status_code == 200
    assert own.json()["decisions"] == []
    assert own.json()["payment_created"] is False
    assert own.json()["order_created"] is False
