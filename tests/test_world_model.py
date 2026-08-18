from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={"external_id": uid, "timezone": "Europe/Paris"},
    )
    assert response.status_code == 200


def test_event_chain_is_verifiable_and_core_changes_emit_events():
    uid = "world-ledger-test-a"
    make_user(uid)

    fact = client.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "demo",
            "key": "capacity",
            "value": {"units": 3},
            "source": "test",
            "confidence": 0.9,
            "sensitivity": "standard",
        },
    )
    assert fact.status_code == 200

    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "test",
            "type": "deadline",
            "payload": {"days_remaining": 5, "relevance": 0.8},
        },
    )
    assert signal.status_code == 200

    integrity = client.get(f"/v1/users/{uid}/world/integrity")
    assert integrity.status_code == 200
    assert integrity.json()["valid"] is True
    assert integrity.json()["event_count"] >= 3
    assert len(integrity.json()["head_hash"]) == 64

    events = client.get(f"/v1/users/{uid}/world/events")
    assert events.status_code == 200
    event_types = {item["event_type"] for item in events.json()}
    assert "user.created" in event_types
    assert "state.fact_observed" in event_types
    assert "signal.observed" in event_types


def test_repeated_experiment_support_promotes_only_to_personal_empirical():
    uid = "world-learning-test-b"
    make_user(uid)

    hypothesis = client.post(
        f"/v1/users/{uid}/world/hypotheses",
        json={
            "name": "small reversible intervention improves target metric",
            "cause_pattern": {"action": "pilot"},
            "effect_pattern": {"metric": "target"},
            "direction": "positive",
        },
    )
    assert hypothesis.status_code == 200
    hypothesis_id = hypothesis.json()["id"]

    for index in range(3):
        experiment = client.post(
            f"/v1/users/{uid}/experiments",
            json={
                "title": f"pilot {index}",
                "hypothesis_id": hypothesis_id,
                "intervention": {"type": "small_pilot", "iteration": index},
                "expected_effects": {"target": {"low": 1, "central": 2, "high": 3}},
                "stop_conditions": ["stop on negative signal"],
                "rollback_plan": {"action": "restore previous state"},
                "reversible": True,
            },
        )
        assert experiment.status_code == 200
        experiment_id = experiment.json()["id"]

        authorized = client.post(
            f"/v1/experiments/{experiment_id}/authorize",
            json={"confirm": f"AUTHORIZE {experiment_id}"},
        )
        assert authorized.status_code == 200
        assert client.post(f"/v1/experiments/{experiment_id}/start").status_code == 200

        observed = client.post(
            f"/v1/experiments/{experiment_id}/observations",
            json={
                "metrics": {"target": 2 + index},
                "verdict": "supports",
                "quality": 0.8,
                "notes": "synthetic controlled observation",
            },
        )
        assert observed.status_code == 200
        assert client.post(f"/v1/experiments/{experiment_id}/complete").status_code == 200

    hypotheses = client.get(f"/v1/users/{uid}/world/hypotheses")
    assert hypotheses.status_code == 200
    item = next(row for row in hypotheses.json() if row["id"] == hypothesis_id)
    assert item["support_count"] == 3
    assert item["claim_level"] == "personal_empirical"
    assert item["claim_level"] != "causal_supported"
    assert 0 < item["confidence"] < 1


def test_irreversible_experiment_requires_explicit_ack():
    uid = "world-experiment-test-c"
    make_user(uid)

    experiment = client.post(
        f"/v1/users/{uid}/experiments",
        json={
            "title": "irreversible test",
            "intervention": {"type": "synthetic"},
            "reversible": False,
        },
    )
    assert experiment.status_code == 200
    experiment_id = experiment.json()["id"]

    refused = client.post(
        f"/v1/experiments/{experiment_id}/authorize",
        json={"confirm": f"AUTHORIZE {experiment_id}"},
    )
    assert refused.status_code == 400

    allowed = client.post(
        f"/v1/experiments/{experiment_id}/authorize",
        json={
            "confirm": f"AUTHORIZE {experiment_id}",
            "irreversible_ack": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["authorization_status"] == "authorized"


def test_world_model_is_in_sovereign_export_and_deletion():
    uid = "world-privacy-test-d"
    make_user(uid)
    created = client.post(
        f"/v1/users/{uid}/world/hypotheses",
        json={
            "name": "exportable hypothesis",
            "cause_pattern": {"x": 1},
            "effect_pattern": {"y": 1},
        },
    )
    assert created.status_code == 200

    export = client.get(f"/v1/users/{uid}/export")
    assert export.status_code == 200
    body = export.json()
    assert body["world_events"]
    assert body["world_hypotheses"]
    assert body["secrets_included"] is False

    deleted = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": f"DELETE {uid}"},
    )
    assert deleted.status_code == 200
    assert client.get(f"/v1/users/{uid}/world/events").status_code == 404
