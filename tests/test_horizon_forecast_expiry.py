from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _tag() -> str:
    return uuid4().hex[:10]


def _setup(tag: str, *, with_materialization_rule: bool = True):
    uid = f"expiry-{tag}"
    user = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert user.status_code == 200, user.text

    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"expiry-event-{tag}",
            "event_type": "extreme_heat",
            "title": "Synthetic heat event",
            "summary": "Synthetic event for expiry tests.",
            "geography": ["FR"],
            "source": "synthetic-official",
            "source_url": "https://example.invalid/event",
            "source_reliability": 0.95,
            "raw_facts": {"synthetic": True},
            "occurred_at": "2020-07-01T06:00:00Z",
            "first_observed_at": "2020-07-01T06:00:00Z",
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    provenance = {
        "type": "synthetic-expiry-test",
        "forecast_expiry_grace_hours": 12,
    }
    if with_materialization_rule:
        provenance["materialization_signal_types"] = ["stockout_reports"]
        provenance["materialization_min_reliability"] = 0.65
        provenance["materialization_strong_source_reliability"] = 0.85
        provenance["materialization_min_normalized_score"] = 0.5

    pattern = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"expiry-pattern-{tag}",
            "name": "Heat to shortage expiry test",
            "event_types": ["extreme_heat"],
            "required_signal_types": ["search_interest"],
            "predicted_response": "A visible shortage may emerge within the declared window.",
            "mechanism_chain": ["heat", "search", "buying", "stock pressure", "visible shortage"],
            "expected_lag_hours_low": 12,
            "expected_lag_hours_high": 48,
            "confidence": 0.8,
            "support_count": 0,
            "contradiction_count": 0,
            "provenance": provenance,
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert pattern.status_code == 200, pattern.text
    pattern_id = pattern.json()["id"]

    search = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"expiry-search-{tag}",
            "signal_type": "search_interest",
            "source": "synthetic-search",
            "geography": ["FR"],
            "value": 300,
            "baseline": 100,
            "normalized_score": 2.0,
            "direction": "up",
            "reliability": 0.9,
            "evidence": {"synthetic": True},
            "observed_at": "2020-07-02T06:00:00Z",
        },
    )
    assert search.status_code == 200, search.text

    forecast = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-07-02T12:00:00Z", "mode": "backtest"},
    )
    assert forecast.status_code == 200, forecast.text
    own = [item for item in forecast.json()["forecasts"] if item["pattern_id"] == pattern_id]
    assert len(own) == 1
    return uid, event_id, pattern_id, own[0]["id"]


def _stockout(event_id: int, tag: str, observed_at: str):
    response = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"expiry-stockout-{tag}-{uuid4().hex[:6]}",
            "signal_type": "stockout_reports",
            "source": "synthetic-official-stock",
            "geography": ["FR"],
            "value": 1,
            "baseline": 0,
            "normalized_score": 1.0,
            "direction": "up",
            "reliability": 0.95,
            "evidence": {"synthetic": True},
            "observed_at": observed_at,
        },
    )
    assert response.status_code == 200, response.text


def test_forecast_stays_open_until_deadline_then_expires_as_false():
    tag = _tag()
    uid, _, _, forecast_id = _setup(tag)
    # onset_high = Jul 3 06:00, grace = 12h, deadline = Jul 3 18:00.
    early = client.post(
        "/v1/horizon/expiry/scan",
        json={"mode": "backtest", "as_of": "2020-07-03T17:59:00Z", "forecast_ids": [forecast_id]},
    )
    assert early.status_code == 200, early.text
    assert forecast_id in early.json()["still_open_forecast_ids"]

    expired = client.post(
        "/v1/horizon/expiry/scan",
        json={"mode": "backtest", "as_of": "2020-07-03T18:01:00Z", "forecast_ids": [forecast_id]},
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["expired_forecast_ids"] == [forecast_id]
    assert expired.json()["late_occurrence_counts_as_success"] is False

    calibration = client.get(f"/v1/horizon/users/{uid}/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["resolved"] == 1
    assert calibration.json()["weighted_precision"] == 0.0

    detections = client.get("/v1/horizon/expiry/detections?limit=500")
    own = [item for item in detections.json() if item["forecast_id"] == forecast_id]
    assert len(own) == 1
    assert own[0]["expiry_deadline"].startswith("2020-07-03T18:00:00")


def test_late_materialization_cannot_retroactively_rescue_forecast():
    tag = _tag()
    uid, event_id, _, forecast_id = _setup(tag)
    _stockout(event_id, tag, "2020-07-04T12:00:00Z")

    materialization = client.post(
        "/v1/horizon/materialization/scan",
        json={"mode": "backtest", "as_of": "2020-07-04T13:00:00Z", "forecast_ids": [forecast_id]},
    )
    assert materialization.status_code == 200, materialization.text
    assert forecast_id not in materialization.json()["resolved_forecast_ids"]
    assert materialization.json()["late_occurrence_counts_as_success"] is False

    expired = client.post(
        "/v1/horizon/expiry/scan",
        json={"mode": "backtest", "as_of": "2020-07-04T13:00:00Z", "forecast_ids": [forecast_id]},
    )
    assert expired.status_code == 200, expired.text
    assert forecast_id in expired.json()["expired_forecast_ids"]

    calibration = client.get(f"/v1/horizon/users/{uid}/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["weighted_precision"] == 0.0


def test_in_window_materialization_wins_before_expiry():
    tag = _tag()
    uid, event_id, _, forecast_id = _setup(tag)
    _stockout(event_id, tag, "2020-07-03T12:00:00Z")

    scan = client.post(
        "/v1/horizon/expiry/scan",
        json={"mode": "backtest", "as_of": "2020-07-04T12:00:00Z", "forecast_ids": [forecast_id]},
    )
    assert scan.status_code == 200, scan.text
    assert forecast_id not in scan.json()["expired_forecast_ids"]

    calibration = client.get(f"/v1/horizon/users/{uid}/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["weighted_precision"] == 1.0
    assert calibration.json()["mean_predictive_lead_time_hours"] == 24.0


def test_no_materialization_rule_is_not_auto_labeled_false():
    tag = _tag()
    _, _, _, forecast_id = _setup(tag, with_materialization_rule=False)
    scan = client.post(
        "/v1/horizon/expiry/scan",
        json={"mode": "backtest", "as_of": "2020-07-10T00:00:00Z", "forecast_ids": [forecast_id]},
    )
    assert scan.status_code == 200, scan.text
    assert forecast_id in scan.json()["no_materialization_rule_forecast_ids"]
    assert forecast_id not in scan.json()["expired_forecast_ids"]


def test_expiry_route_is_mounted():
    response = client.post("/v1/horizon/expiry/scan", json={"mode": "live", "max_forecasts": 1})
    assert response.status_code != 404
