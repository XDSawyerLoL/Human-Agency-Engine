from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={"external_id": uid, "timezone": "Europe/Paris"},
    )
    assert response.status_code == 200


def test_state_fact_replacement_and_history():
    uid = "state-graph-test-a"
    make_user(uid)

    for value in (1, 2):
        response = client.post(
            f"/v1/users/{uid}/state/facts",
            json={
                "domain": "demo",
                "key": "counter",
                "value": {"number": value},
                "source": "test",
                "confidence": 1.0,
                "sensitivity": "standard",
            },
        )
        assert response.status_code == 200

    current = client.get(f"/v1/users/{uid}/state/facts")
    assert current.status_code == 200
    assert len(current.json()) == 1
    assert current.json()[0]["value"]["number"] == 2

    history = client.get(
        f"/v1/users/{uid}/state/facts",
        params={"include_history": "true"},
    )
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert sum(1 for item in history.json() if item["superseded"]) == 1

    snapshot = client.get(f"/v1/users/{uid}/state")
    assert snapshot.status_code == 200
    assert snapshot.json()["domains"]["demo"]["counter"]["value"]["number"] == 2


def test_invalid_expiry_is_rejected():
    uid = "state-graph-test-b"
    make_user(uid)
    response = client.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "demo",
            "key": "temporary",
            "value": {"enabled": True},
            "observed_at": "2026-08-18T12:00:00",
            "expires_at": "2026-08-18T11:00:00",
        },
    )
    assert response.status_code == 400


def test_intent_lifecycle():
    uid = "state-graph-test-c"
    make_user(uid)
    created = client.post(
        f"/v1/users/{uid}/intents",
        json={"kind": "demo", "statement": "test objective", "priority": 0.6},
    )
    assert created.status_code == 200
    intent_id = created.json()["id"]

    updated = client.patch(
        f"/v1/intents/{intent_id}",
        json={"priority": 0.95, "active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 0.95
    assert updated.json()["active"] is False

    active = client.get(f"/v1/users/{uid}/intents", params={"active_only": "true"})
    assert active.status_code == 200
    assert active.json() == []
