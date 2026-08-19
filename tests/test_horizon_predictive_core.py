from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _create_user(uid: str):
    response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert response.status_code == 200, response.text


def _create_heat_event(tag: str):
    response = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"heat-{tag}",
            "event_type": "extreme_heat",
            "title": "Exceptional heat warning",
            "summary": "Several days of exceptional heat are forecast.",
            "geography": ["FR"],
            "source": "synthetic-weather-authority",
            "source_url": "https://example.invalid/weather",
            "source_reliability": 0.95,
            "raw_facts": {
                "temperature_c": 41,
                "intent_keywords": ["cooling"],
                "fact_only": True,
            },
            "occurred_at": "2020-07-01T06:00:00Z",
            "first_observed_at": "2020-07-01T06:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _create_pattern(tag: str, knowledge_at: str = "2019-01-01T00:00:00Z"):
    response = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"heat-demand-{tag}",
            "name": "Heat-driven cooling demand surge",
            "event_types": ["extreme_heat"],
            "required_signal_types": ["search_interest"],
            "predicted_response": "Demand for cooling equipment may surge before widespread stock shortages.",
            "mechanism_chain": [
                "extreme heat warning",
                "anticipatory search behavior",
                "purchase acceleration",
                "inventory compression",
                "visible shortage",
            ],
            "expected_lag_hours_low": 48,
            "expected_lag_hours_high": 144,
            "confidence": 0.85,
            "support_count": 12,
            "contradiction_count": 2,
            "provenance": {"type": "synthetic-test-pattern"},
            "knowledge_available_at": knowledge_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _add_signal(event_id: int, tag: str, signal_type: str, observed_at: str, score: float = 3.0):
    response = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"{signal_type}-{tag}-{uuid4().hex[:8]}",
            "signal_type": signal_type,
            "source": "synthetic-signal-source",
            "geography": ["FR"],
            "value": 400,
            "baseline": 100,
            "normalized_score": score,
            "direction": "up",
            "reliability": 0.9,
            "evidence": {"synthetic": True},
            "observed_at": observed_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_horizon_separates_facts_social_signals_and_prediction_without_fake_probability():
    tag = uuid4().hex[:10]
    uid = _uid("horizon-layers")
    _create_user(uid)
    event_id = _create_heat_event(tag)
    pattern_id = _create_pattern(tag)
    _add_signal(event_id, tag, "search_interest", "2020-07-02T06:00:00Z")

    response = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-07-02T12:00:00Z", "mode": "backtest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["numeric_probabilities_enabled"] is False
    assert body["backtest_no_future_leakage_guards"] is True
    own = [item for item in body["forecasts"] if item["pattern_id"] == pattern_id]
    assert len(own) == 1

    forecast = own[0]
    assert forecast["fact_layer"]["raw_facts"]["temperature_c"] == 41
    assert forecast["social_signal_layer"][0]["signal_type"] == "search_interest"
    assert forecast["forecast_layer"]["predicted_outcome"].startswith("Demand for cooling equipment")
    assert forecast["forecast_layer"]["predictive_score_is_probability"] is False
    interval = forecast["forecast_layer"]["probability_interval"]
    assert interval == {"low": None, "mid": None, "high": None, "basis": "not_calibrated"}
    assert forecast["forecast_layer"]["likelihood_band"] in {"plausible", "strong"}


def test_backtest_never_sees_signals_or_behavior_knowledge_from_after_cutoff():
    tag = uuid4().hex[:10]
    uid = _uid("horizon-cutoff")
    _create_user(uid)
    event_id = _create_heat_event(tag)
    early_pattern_id = _create_pattern(f"early-{tag}", knowledge_at="2019-01-01T00:00:00Z")
    future_pattern_id = _create_pattern(f"future-{tag}", knowledge_at="2020-07-05T00:00:00Z")
    early = _add_signal(event_id, tag, "search_interest", "2020-07-02T06:00:00Z")
    late = _add_signal(event_id, tag, "stock_availability", "2020-07-05T06:00:00Z", score=-3.0)

    response = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-07-03T00:00:00Z", "mode": "backtest"},
    )
    assert response.status_code == 200, response.text
    forecasts = response.json()["forecasts"]
    pattern_ids = {item["pattern_id"] for item in forecasts}
    assert early_pattern_id in pattern_ids
    assert future_pattern_id not in pattern_ids
    serialized = str(forecasts)
    assert early["signal_key"] in serialized
    assert late["signal_key"] not in serialized

    before_event = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-06-30T23:59:00Z", "mode": "backtest"},
    )
    assert before_event.status_code == 400
    assert "not observable" in before_event.text.lower()


def test_resolution_measures_predictive_and_actionable_lead_time():
    tag = uuid4().hex[:10]
    uid = _uid("horizon-lead")
    _create_user(uid)
    event_id = _create_heat_event(tag)
    pattern_id = _create_pattern(tag)
    _add_signal(event_id, tag, "search_interest", "2020-07-02T06:00:00Z")

    forecast_response = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-07-03T12:00:00Z", "mode": "backtest"},
    )
    assert forecast_response.status_code == 200, forecast_response.text
    own = [item for item in forecast_response.json()["forecasts"] if item["pattern_id"] == pattern_id]
    assert len(own) == 1
    forecast_id = own[0]["id"]

    resolved = client.put(
        f"/v1/horizon/forecasts/{forecast_id}/resolution",
        json={
            "outcome_occurred": True,
            "outcome_summary": "Cooling equipment shortage became broadly visible.",
            "correctness": "confirmed",
            "became_obvious_at": "2020-07-05T12:00:00Z",
            "personal_action_at": "2020-07-04T12:00:00Z",
            "notes": "Synthetic historical validation case.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["predictive_lead_time_hours"] == 48.0
    assert body["actionable_lead_time_hours"] == 24.0

    calibration = client.get(f"/v1/horizon/users/{uid}/calibration")
    assert calibration.status_code == 200
    summary = calibration.json()
    assert summary["resolved"] == 1
    assert summary["weighted_precision"] == 1.0
    assert summary["mean_predictive_lead_time_hours"] == 48.0
    assert summary["probability_calibration_enabled"] is False
