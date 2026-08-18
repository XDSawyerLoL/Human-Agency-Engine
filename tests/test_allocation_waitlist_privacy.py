from fastapi.testclient import TestClient

from app.main import app
from tests.test_privacy_preserving_allocation import _allocate, _prepared_oversubscribed_group

client = TestClient(app)


def test_capacity_below_participant_count_keeps_waitlist_private():
    category = "allocation-private-waitlist"
    members, offer, _ = _prepared_oversubscribed_group(
        category,
        users=10,
        quantity=1,
        capacity=5,
    )
    public = _allocate(offer["offer_id"])

    assert public["allocation_current"] is True
    summary = public["allocation"]
    assert summary["committed_user_count"] == 10
    assert summary["committed_quantity"] == 10
    assert summary["capacity_quantity"] == 5
    assert summary["allocated_user_count"] == 5
    assert summary["allocated_quantity"] == 5
    assert summary["oversubscribed"] is True
    assert public["member_identities_included"] is False
    assert public["private_allocations_included"] is False

    statuses = []
    allocation_entries = []
    for uid, _, membership in members:
        own = client.get(f"/v1/collective-allocation/users/{uid}")
        assert own.status_code == 200
        assert own.json()["scope"] == "self_only"
        assert own.json()["shared_with_responders"] is False
        assert len(own.json()["allocations"]) == 1
        item = own.json()["allocations"][0]
        statuses.append((item["status"], item["allocated_quantity"]))
        allocation_entries.append(item["allocation_entry_id"])

    assert sorted(statuses) == [("allocated", 1)] * 5 + [("waitlisted", 0)] * 5

    serialized_public = str(public)
    for uid, _, membership in members:
        assert uid not in serialized_public
        assert membership["membership_id"] not in serialized_public
    for entry_id in allocation_entries:
        assert entry_id not in serialized_public
