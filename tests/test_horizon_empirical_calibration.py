from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.horizon_calibration import _wilson_interval

client = TestClient(app)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _create_user(uid: str) -> None:
    response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert response.status_code == 200, response.text


def _create_forecast(uid: str, tag: str, event_time: str, as_of: str) -> int:
    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"cal-event-{tag}",
            "event_type": "supply_disruption",
            "title": "Synthetic supply disruption",
            "summary": "Synthetic calibration event.",
            "geography": ["FR"],
            "source": "synthetic-calibration-source",
            "source_url": "https://example.invalid/calibration",
            "source_reliability": 0.9,
            "raw_facts": {"fact_only": True},
            "occurred_at": event_time,
            "first_observed_at": event_time,
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    pattern = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"cal-pattern-{tag}",
            "name": "Synthetic calibration pattern",
            "event_types": ["supply_disruption"],
            "required_signal_types": [],
            "predicted_response": "A visible supply effect may materialize.",
            "mechanism_chain": ["disruption", "adaptation", "visible effect"],
            "expected_lag_hours_low": 12,
            "expected_lag_hours_high": 72,
            "confidence": 0.8,
            "support_count": 0,
            "contradiction_count": 0,
            "provenance": {"type": "synthetic-calibration-test"},
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert pattern.status_code == 200, pattern.text
    pattern_id = pattern.json()["id"]

    forecast = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": as_of, "mode": "backtest"},
    )
    assert forecast.status_code == 200, forecast.text
    own = [row for row in forecast.json()["forecasts"] if row["pattern_id"] == pattern_id]
    assert len(own) == 1
    return own[0]["id"]


def test_wilson_interval_is_bounded_and_contains_observed_rate():
    low, high = _wilson_interval(5, 10)
    assert low is not None and high is not None
    assert 0.0 <= low < 0.5 < high <= 1.0


def test_empirical_calibration_counts_successes_and_failures_without_enabling_probability():
    uid = _uid("horizon-calibration")
    _create_user(uid)

    confirmed_id = _create_forecast(
        uid,
        uuid4().hex[:8],
        "2020-01-01T00:00:00Z",
        "2020-01-01T06:00:00Z",
    )
    false_id = _create_forecast(
        uid,
        uuid4().hex[:8],
        "2020-02-01T00:00:00Z",
        "2020-02-01T06:00:00Z",
    )

    confirmed = client.put(
        f"/v1/horizon/forecasts/{confirmed_id}/resolution",
        json={
            "outcome_occurred": True,
            "outcome_summary": "Synthetic effect became visible.",
            "correctness": "confirmed",
            "became_obvious_at": "2020-01-02T06:00:00Z",
            "personal_action_at": None,
            "notes": "Synthetic confirmed calibration label.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    failed = client.put(
        f"/v1/horizon/forecasts/{false_id}/resolution",
        json={
            "outcome_occurred": False,
            "outcome_summary": "Synthetic effect did not occur.",
            "correctness": "false",
            "became_obvious_at": None,
            "personal_action_at": None,
            "notes": "Synthetic negative calibration label.",
        },
    )
    assert failed.status_code == 200, failed.text

    response = client.get(f"/v1/horizon/calibration/users/{uid}/profile")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["engine"] == "horizon-empirical-calibration-v0.2"
    assert body["mode"] == "backtest"
    assert body["decisive_labels"] == 2
    assert body["weighted_precision"] == 0.5
    assert body["global_binary_evidence"]["binary_labels"] == 2
    assert body["global_binary_evidence"]["successes"] == 1
    assert body["global_binary_evidence"]["failures"] == 1
    assert body["global_binary_evidence"]["distinct_events"] == 2
    assert body["global_binary_evidence"]["observed_success_rate"] == 0.5
    assert body["probability_calibration_ready"] is False
    assert body["probability_calibration_enabled"] is False
    assert body["critical_semantics"]["predictive_score_is_probability"] is False
    assert body["critical_semantics"]["partial_labels_used_for_probability_rate"] is False
    assert body["score_alignment_is_probability_calibration"] is False


def test_historical_calibration_cutoff_excludes_negative_label_entered_later():
    uid = _uid("horizon-calibration-cutoff")
    _create_user(uid)

    forecast_id = _create_forecast(
        uid,
        uuid4().hex[:8],
        "2020-03-01T00:00:00Z",
        "2020-03-01T06:00:00Z",
    )
    failed = client.put(
        f"/v1/horizon/forecasts/{forecast_id}/resolution",
        json={
            "outcome_occurred": False,
            "outcome_summary": "No materialization.",
            "correctness": "false",
            "became_obvious_at": None,
            "personal_action_at": None,
            "notes": "Entered after the historical cutoff.",
        },
    )
    assert failed.status_code == 200, failed.text

    historical = client.get(
        f"/v1/horizon/calibration/users/{uid}/profile",
        params={"mode": "backtest", "as_of": "2020-12-31T23:59:59Z"},
    )
    assert historical.status_code == 200, historical.text
    body = historical.json()
    assert body["decisive_labels"] == 0
    assert body["global_binary_evidence"]["binary_labels"] == 0
    assert body["probability_calibration_ready"] is False
    assert body["critical_semantics"]["historical_cutoff_excludes_labels_not_yet_available"] is True
