from fastapi.testclient import TestClient

from app.main import app
from tests.test_post_allocation_acceptance import _accept, _private_allocation
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group

client = TestClient(app)


def _accept_first(members, count: int, allocation_set_hash: str):
    accepted = []
    for uid, _, _ in members:
        private = _private_allocation(uid)
        if private["allocated_quantity"] <= 0:
            continue
        response = _accept(uid, private, allocation_set_hash)
        assert response.status_code == 200, response.text
        accepted.append((uid, private, response.json()))
        if len(accepted) == count:
            break
    assert len(accepted) == count
    return accepted


def test_ten_exact_acceptances_publish_ready_state_but_create_no_payment_or_order():
    category = "settlement-ready-ten"
    members, offer, _ = _prepared_oversubscribed_group(category, users=10, quantity=1, capacity=10)
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    accepted = _accept_first(members, 10, allocation_set_hash)

    assessed = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert assessed.status_code == 200, assessed.text
    body = assessed.json()
    assert body["published"] is True
    assert body["state"] == "ready_for_settlement_preparation"
    assert body["settlement_ready"] is True
    assert body["accepted_user_count"] == 10
    assert body["accepted_quantity"] == 10
    assert body["allocated_user_count"] == 10
    assert body["allocated_quantity"] == 10
    assert body["all_allocated_users_accepted"] is True
    assert body["commercial_minimum_met"] is True
    assert body["capacity_ok"] is True
    assert body["exact_total_amount"] == 700.0
    assert body["privacy"]["minimum_anonymity_set"] == 10
    assert body["privacy"]["lower_anonymity_override_supported"] is False
    assert body["privacy"]["formal_differential_privacy"] is False
    assert body["external_dispatch_enabled"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False

    serialized = str(body)
    for uid, _, decision in accepted:
        assert uid not in serialized
        assert decision["decision_id"] not in serialized
        assert decision["decision_hash"] not in serialized


def test_nine_acceptances_hide_counts_receipt_and_commercial_state():
    category = "settlement-hidden-nine"
    members, offer, _ = _prepared_oversubscribed_group(category, users=10, quantity=1, capacity=10)
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    accepted = _accept_first(members, 9, allocation_set_hash)

    assessed = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert assessed.status_code == 200, assessed.text
    body = assessed.json()
    assert body["published"] is False
    assert body["state"] == "below_settlement_privacy_threshold"
    assert body["settlement_ready"] is False
    assert body["accepted_user_count"] is None
    assert body["accepted_quantity"] is None
    assert body["allocated_user_count"] is None
    assert body["allocated_quantity"] is None
    assert body["commercial_minimum_met"] is None
    assert body["all_allocated_users_accepted"] is None
    assert "receipt_id" not in body
    assert body["payment_created"] is False
    assert body["order_created"] is False

    serialized = str(body)
    for uid, _, decision in accepted:
        assert uid not in serialized
        assert decision["decision_id"] not in serialized
        assert decision["decision_hash"] not in serialized


def test_five_allocated_users_cannot_lower_default_anonymity_even_if_all_accept():
    category = "settlement-no-small-anonymity"
    members, offer, _ = _prepared_oversubscribed_group(category, users=10, quantity=1, capacity=5)
    allocation = _allocate(offer["offer_id"])
    assert allocation["allocation"]["allocated_user_count"] == 5
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    _accept_first(members, 5, allocation_set_hash)

    assessed = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert assessed.status_code == 200, assessed.text
    body = assessed.json()
    assert body["published"] is False
    assert body["settlement_ready"] is False
    assert body["accepted_user_count"] is None
    assert body["privacy"]["minimum_anonymity_set"] == 10
    assert body["privacy"]["lower_anonymity_override_supported"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False


def test_ten_of_twelve_acceptances_can_be_published_but_are_not_settlement_ready():
    category = "settlement-published-incomplete"
    members, offer, _ = _prepared_oversubscribed_group(category, users=12, quantity=1, capacity=12)
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    _accept_first(members, 10, allocation_set_hash)

    assessed = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert assessed.status_code == 200, assessed.text
    body = assessed.json()
    assert body["published"] is True
    assert body["state"] == "acceptance_threshold_met_but_not_ready"
    assert body["accepted_user_count"] == 10
    assert body["allocated_user_count"] == 12
    assert body["all_allocated_users_accepted"] is False
    assert body["settlement_ready"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False


def test_revoking_one_of_ten_acceptances_invalidates_current_readiness_instead_of_exposing_old_ready_state():
    category = "settlement-revocation-stale"
    members, offer, _ = _prepared_oversubscribed_group(category, users=10, quantity=1, capacity=10)
    allocation = _allocate(offer["offer_id"])
    allocation_set_hash = allocation["allocation"]["allocation_set_hash"]
    accepted = _accept_first(members, 10, allocation_set_hash)
    ready = client.post(
        "/v1/collective-settlement/assess",
        json={"offer_id": offer["offer_id"]},
    )
    assert ready.status_code == 200
    assert ready.json()["settlement_ready"] is True

    uid, _, decision = accepted[-1]
    revoked = client.post(
        f"/v1/collective-acceptance/users/{uid}/decisions/{decision['decision_id']}/revoke",
        json={"confirm": f"REVOKE ALLOCATION ACCEPTANCE {decision['decision_id']}"},
    )
    assert revoked.status_code == 200

    current = client.get(f"/v1/collective-settlement/offers/{offer['offer_id']}")
    assert current.status_code == 200
    body = current.json()
    assert body["published"] is False
    assert body["state"] == "no_current_assessed_settlement_readiness"
    assert body["settlement_ready"] is False
    assert body["accepted_user_count"] is None
    assert body["accepted_quantity"] is None
    assert body["payment_created"] is False
    assert body["order_created"] is False
