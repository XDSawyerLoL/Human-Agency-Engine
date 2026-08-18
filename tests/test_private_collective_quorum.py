from fastapi.testclient import TestClient

from app.main import app
from tests.test_collective_offer_protocol import _cohort, _open_window, _seller, _signed_offer

client = TestClient(app)


def _offer(category: str, *, budgets=None, minimum_quantity: int = 8, maximum_quantity: int = 100):
    members = _cohort(category, budgets=budgets)
    window = _open_window(members[0][2]["cohort_key"])
    private, public_b64 = _seller()
    signed = _signed_offer(
        window["window_id"],
        private,
        public_b64,
        offer_id=f"{category}-offer",
        minimum_collective_quantity=minimum_quantity,
        maximum_collective_quantity=maximum_quantity,
    )
    accepted = client.post(
        f"/v1/collective-market/windows/{window['window_id']}/offers",
        json=signed,
    )
    assert accepted.status_code == 200, accepted.text
    return members, window, accepted.json()


def _evaluate(uid: str, membership_id: str, offer_id: str):
    response = client.post(
        f"/v1/collective-market/users/{uid}/evaluate",
        json={"membership_id": membership_id, "offer_id": offer_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _commit(uid: str, membership_id: str, offer: dict):
    response = client.post(
        f"/v1/collective-quorum/users/{uid}/commit",
        json={
            "membership_id": membership_id,
            "offer_id": offer["offer_id"],
            "confirm": f"CONDITIONALLY COMMIT {offer['offer_id']} {offer['offer_hash'][-12:]}",
        },
    )
    return response


def test_nine_private_commitments_hide_counts_and_even_commercial_minimum_state():
    category = "quorum-hidden-nine"
    members, _, offer = _offer(category, minimum_quantity=8)
    commitment_bodies = []
    for uid, _, membership in members[:9]:
        evaluation = _evaluate(uid, membership["membership_id"], offer["offer_id"])
        assert evaluation["provisional_eligible"] is True
        committed = _commit(uid, membership["membership_id"], offer)
        assert committed.status_code == 200, committed.text
        commitment_bodies.append(committed.json())

    quorum = client.get(f"/v1/collective-quorum/offers/{offer['offer_id']}")
    assert quorum.status_code == 200
    body = quorum.json()
    assert body["published"] is False
    assert body["state"] == "below_commitment_privacy_threshold"
    assert body["committed_user_count"] is None
    assert body["committed_quantity"] is None
    assert body["commercial_minimum_met"] is None
    assert body["quorum_publicly_confirmed"] is False
    assert body["payment_created"] is False
    assert body["order_created"] is False
    assert body["privacy"]["minimum_distinct_committed_users_for_publication"] == 10
    assert body["privacy"]["formal_differential_privacy"] is False

    serialized = str(body)
    for uid, _, membership in members[:9]:
        assert uid not in serialized
        assert membership["membership_id"] not in serialized
    for commitment in commitment_bodies:
        assert commitment["commitment_id"] not in serialized


def test_tenth_distinct_commitment_publishes_only_safe_quorum_and_no_order():
    category = "quorum-published-ten"
    members, _, offer = _offer(category, minimum_quantity=8)
    commitments = []
    evaluations = []
    for uid, _, membership in members:
        evaluation = _evaluate(uid, membership["membership_id"], offer["offer_id"])
        evaluations.append(evaluation)
        committed = _commit(uid, membership["membership_id"], offer)
        assert committed.status_code == 200, committed.text
        commitments.append(committed.json())

    quorum = client.get(f"/v1/collective-quorum/offers/{offer['offer_id']}")
    assert quorum.status_code == 200
    body = quorum.json()
    assert body["published"] is True
    assert body["state"] == "commitment_privacy_threshold_met"
    assert body["committed_user_count"] == 10
    assert body["committed_quantity"] == 10
    assert body["commercial_minimum_quantity"] == 8
    assert body["commercial_minimum_met"] is True
    assert body["quorum_publicly_confirmed"] is True
    assert body["commitment_set_hash"].startswith("sha256:")
    assert body["payment_created"] is False
    assert body["order_created"] is False
    assert body["privacy"]["user_ids_included"] is False
    assert body["privacy"]["commitment_ids_included"] is False
    assert body["privacy"]["evaluation_ids_included"] is False
    assert body["privacy"]["individual_quantities_included"] is False

    serialized = str(body)
    for uid, _, membership in members:
        assert uid not in serialized
        assert membership["membership_id"] not in serialized
    for commitment in commitments:
        assert commitment["commitment_id"] not in serialized
    for evaluation in evaluations:
        assert evaluation["evaluation_id"] not in serialized


def test_revoking_tenth_commitment_immediately_rehides_quorum():
    category = "quorum-revoke-ten"
    members, _, offer = _offer(category, minimum_quantity=8)
    commitments = []
    for uid, _, membership in members:
        _evaluate(uid, membership["membership_id"], offer["offer_id"])
        committed = _commit(uid, membership["membership_id"], offer)
        assert committed.status_code == 200
        commitments.append(committed.json())

    before = client.get(f"/v1/collective-quorum/offers/{offer['offer_id']}").json()
    assert before["published"] is True
    assert before["committed_user_count"] == 10

    uid = members[-1][0]
    commitment = commitments[-1]
    revoked = client.post(
        f"/v1/collective-quorum/users/{uid}/commitments/{commitment['commitment_id']}/revoke",
        json={"confirm": f"REVOKE CONDITIONAL COMMITMENT {commitment['commitment_id']}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    after = client.get(f"/v1/collective-quorum/offers/{offer['offer_id']}").json()
    assert after["published"] is False
    assert after["state"] == "below_commitment_privacy_threshold"
    assert after["committed_user_count"] is None
    assert after["committed_quantity"] is None
    assert after["commercial_minimum_met"] is None


def test_private_agent_must_mark_offer_eligible_before_commitment_is_accepted():
    category = "quorum-private-fit-required"
    budgets = [60] + [100] * 9
    members, _, offer = _offer(category, budgets=budgets, minimum_quantity=8)
    uid, _, membership = members[0]

    evaluation = _evaluate(uid, membership["membership_id"], offer["offer_id"])
    assert evaluation["provisional_eligible"] is False
    committed = _commit(uid, membership["membership_id"], offer)
    assert committed.status_code == 400
    assert "private agent evaluation" in committed.text.lower()

    own = client.get(f"/v1/collective-quorum/users/{uid}/commitments")
    assert own.status_code == 200
    assert own.json()["commitments"] == []
    assert own.json()["shared_with_responders"] is False
    assert own.json()["payment_created"] is False
    assert own.json()["order_created"] is False


def test_public_quorum_reports_oversubscription_without_allocating_or_ordering():
    category = "quorum-oversubscribed"
    members, _, offer = _offer(category, minimum_quantity=8, maximum_quantity=9)
    for uid, _, membership in members:
        _evaluate(uid, membership["membership_id"], offer["offer_id"])
        assert _commit(uid, membership["membership_id"], offer).status_code == 200

    body = client.get(f"/v1/collective-quorum/offers/{offer['offer_id']}").json()
    assert body["published"] is True
    assert body["commercial_minimum_met"] is True
    assert body["capacity_exceeded"] is True
    assert body["allocation_required"] is True
    assert body["quorum_publicly_confirmed"] is True
    assert body["payment_created"] is False
    assert body["order_created"] is False
