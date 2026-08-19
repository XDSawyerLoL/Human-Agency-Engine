from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(uid: str, country: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "country": country,
            "currency": "EUR",
            "timezone": "Europe/Paris",
        },
    )
    assert response.status_code == 200, response.text


def _setup(tag: str):
    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"impact-heat-{tag}",
            "event_type": "extreme_heat",
            "title": "Exceptional heat warning",
            "summary": "Several days above 40C are forecast.",
            "geography": ["FR"],
            "source": "synthetic-weather-authority",
            "source_url": "https://example.invalid/weather",
            "source_reliability": 0.97,
            "raw_facts": {
                "temperature_c": 41,
                "exposure_keys": ["housing.cooling"],
                "intent_keywords": ["cooling"],
                "fact_only": True,
            },
            "occurred_at": "2020-07-01T06:00:00Z",
            "first_observed_at": "2020-07-01T06:00:00Z",
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    pattern = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"impact-pattern-{tag}",
            "name": "Heat demand cascade",
            "event_types": ["extreme_heat"],
            "required_signal_types": ["search_interest"],
            "predicted_response": "Cooling demand may accelerate before visible stock shortages.",
            "mechanism_chain": [
                "heat threat perception",
                "cooling search acceleration",
                "purchase acceleration",
                "inventory compression",
            ],
            "expected_lag_hours_low": 48,
            "expected_lag_hours_high": 144,
            "confidence": 0.86,
            "support_count": 20,
            "contradiction_count": 3,
            "provenance": {
                "stage_signal_types": {
                    "0": ["heat_mentions"],
                    "1": ["search_interest"],
                    "2": ["purchase_velocity"],
                    "3": ["stock_availability"],
                }
            },
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert pattern.status_code == 200, pattern.text
    pattern_id = pattern.json()["id"]

    for signal_type, stage, at in (
        ("heat_mentions", "heat threat perception", "2020-07-01T10:00:00Z"),
        ("search_interest", "cooling search acceleration", "2020-07-02T06:00:00Z"),
    ):
        signal = client.post(
            f"/v1/horizon/events/{event_id}/signals",
            json={
                "signal_key": f"impact-{signal_type}-{tag}-{uuid4().hex[:6]}",
                "signal_type": signal_type,
                "source": f"synthetic-{signal_type}",
                "geography": ["FR"],
                "value": 400,
                "baseline": 100,
                "normalized_score": 3.0,
                "direction": "up",
                "reliability": 0.95,
                "evidence": {"cascade_stage": stage},
                "observed_at": at,
            },
        )
        assert signal.status_code == 200, signal.text
    return event_id, pattern_id


def test_same_world_event_produces_different_personal_attention():
    tag = uuid4().hex[:10]
    exposed = f"impact-exposed-{tag}"
    remote = f"impact-remote-{tag}"
    _create_user(exposed, "FR")
    _create_user(remote, "ES")
    event_id, pattern_id = _setup(tag)

    fact = client.post(
        f"/v1/users/{exposed}/state/facts",
        json={
            "domain": "housing",
            "key": "cooling",
            "value": {"available": False},
            "source": "user",
            "confidence": 1.0,
            "sensitivity": "personal",
            "observed_at": "2020-06-20T00:00:00Z",
        },
    )
    assert fact.status_code == 200, fact.text
    intent = client.post(
        f"/v1/users/{exposed}/intents",
        json={
            "kind": "resilience",
            "statement": "Keep the household safe and comfortable during cooling emergencies",
            "target": {},
            "priority": 0.9,
        },
    )
    assert intent.status_code == 200, intent.text

    payload = {
        "event_id": event_id,
        "pattern_id": pattern_id,
        "as_of": "2020-07-02T12:00:00Z",
        "mode": "backtest",
    }
    exposed_result = client.post(f"/v1/horizon/impact/users/{exposed}/assess", json=payload)
    remote_result = client.post(f"/v1/horizon/impact/users/{remote}/assess", json=payload)
    assert exposed_result.status_code == 200, exposed_result.text
    assert remote_result.status_code == 200, remote_result.text

    high = exposed_result.json()["assessment"]
    low = remote_result.json()["assessment"]
    assert high["personal_exposure_layer"]["score"] > low["personal_exposure_layer"]["score"]
    assert high["attention_score"] > low["attention_score"]
    assert high["fact_layer"]["raw_facts"]["temperature_c"] == 41
    assert high["collective_behavior_layer"]["current_stage"] == "cooling search acceleration"
    assert high["explanation"]["fact_and_inference_separated"] is True
    assert high["attention_score_is_probability"] is False
    assert exposed_result.json()["raw_information_is_preserved"] is True
    assert exposed_result.json()["action_prescribed"] is False


def test_personal_impact_backtest_does_not_use_future_cascade_stage():
    tag = uuid4().hex[:10]
    uid = f"impact-cutoff-{tag}"
    _create_user(uid, "FR")
    event_id, pattern_id = _setup(tag)

    future_signal = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"future-stock-{tag}",
            "signal_type": "stock_availability",
            "source": "synthetic-stock",
            "geography": ["FR"],
            "value": 10,
            "baseline": 100,
            "normalized_score": -3.0,
            "direction": "down",
            "reliability": 0.95,
            "evidence": {"cascade_stage": "inventory compression"},
            "observed_at": "2020-07-05T12:00:00Z",
        },
    )
    assert future_signal.status_code == 200, future_signal.text

    result = client.post(
        f"/v1/horizon/impact/users/{uid}/assess",
        json={
            "event_id": event_id,
            "pattern_id": pattern_id,
            "as_of": "2020-07-02T12:00:00Z",
            "mode": "backtest",
        },
    )
    assert result.status_code == 200, result.text
    assessment = result.json()["assessment"]
    assert assessment["collective_behavior_layer"]["current_stage"] == "cooling search acceleration"
    assert "future-stock" not in str(assessment)
