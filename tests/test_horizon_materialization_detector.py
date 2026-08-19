from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _tag() -> str:
    return uuid4().hex[:10]


def _create_user(tag: str) -> str:
    uid = f"materialization-{tag}"
    response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert response.status_code == 200, response.text
    return uid


def _create_event(tag: str) -> int:
    response = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"materialization-event-{tag}",
            "event_type": "extreme_heat",
            "title": "Extreme heat test event",
            "summary": "Synthetic event for automatic materialization tests.",
            "geography": ["FR"],
            "source": "synthetic-official",
            "source_url": "https://example.invalid/event",
            "source_reliability": 0.95,
            "raw_facts": {"synthetic": True},
            "occurred_at": "2020-07-01T06:00:00Z",
            "first_observed_at": "2020-07-01T06:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _create_pattern(tag: str) -> int:
    response = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"materialization-pattern-{tag}",
            "name": "Cooling demand to visible shortage",
            "event_types": ["extreme_heat"],
            "required_signal_types": ["search_interest"],
            "predicted_response": "Cooling demand may progress to a visible equipment shortage.",
            "mechanism_chain": [
                "heat attention",
                "search acceleration",
                "purchase acceleration",
                "inventory compression",
                "visible shortage",
            ],
            "expected_lag_hours_low": 24,
            "expected_lag_hours_high": 144,
            "confidence": 0.8,
            "support_count": 0,
            "contradiction_count": 0,
            "provenance": {
                "type": "synthetic-materialization-test",
                "materialization_signal_types": ["stockout_reports"],
                "materialization_min_reliability": 0.65,
                "materialization_strong_source_reliability": 0.85,
                "materialization_min_normalized_score": 0.5,
            },
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _signal(
    event_id: int,
    tag: str,
    signal_type: str,
    observed_at: str,
    *,
    source: str,
    reliability: float,
    score: float = 1.0,
):
    response = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"{tag}-{signal_type}-{uuid4().hex[:8]}",
            "signal_type": signal_type,
            "source": source,
            "geography": ["FR"],
            "value": 1,
            "baseline": 0,
            "normalized_score": score,
            "direction": "up",
            "reliability": reliability,
            "evidence": {"synthetic": True},
            "observed_at": observed_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _forecast(uid: str, event_id: int, pattern_id: int) -> int:
    response = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2020-07-03T12:00:00Z", "mode": "backtest"},
    )
    assert response.status_code == 200, response.text
    own = [item for item in response.json()["forecasts"] if item["pattern_id"] == pattern_id]
    assert len(own) == 1
    return own[0]["id"]


def _setup_case(tag: str):
    uid = _create_user(tag)
    event_id = _create_event(tag)
    pattern_id = _create_pattern(tag)
    _signal(
        event_id,
        tag,
        "search_interest",
        "2020-07-02T06:00:00Z",
        source="search-source",
        reliability=0.9,
        score=2.0,
    )
    forecast_id = _forecast(uid, event_id, pattern_id)
    return uid, event_id, pattern_id, forecast_id


def _scan(forecast_id: int, as_of: str):
    return client.post(
        "/v1/horizon/materialization/scan",
        json={
            "mode": "backtest",
            "as_of": as_of,
            "max_forecasts": 500,
            "forecast_ids": [forecast_id],
        },
    )


def test_materialization_requires_post_forecast_final_stage_and_strong_evidence():
    tag = _tag()
    uid, event_id, _, forecast_id = _setup_case(tag)

    _signal(
        event_id,
        tag,
        "stockout_reports",
        "2020-07-03T11:00:00Z",
        source="pre-forecast-source",
        reliability=0.95,
    )
    _signal(
        event_id,
        tag,
        "stock_availability",
        "2020-07-04T06:00:00Z",
        source="inventory-source",
        reliability=0.95,
        score=3.0,
    )
    _signal(
        event_id,
        tag,
        "stockout_reports",
        "2020-07-04T12:00:00Z",
        source="weak-source",
        reliability=0.60,
    )

    unresolved = _scan(forecast_id, "2020-07-04T18:00:00Z")
    assert unresolved.status_code == 200, unresolved.text
    assert forecast_id not in unresolved.json()["resolved_forecast_ids"]

    strong = _signal(
        event_id,
        tag,
        "stockout_reports",
        "2020-07-05T12:00:00Z",
        source="official-stock-source",
        reliability=0.95,
    )
    resolved = _scan(forecast_id, "2020-07-06T00:00:00Z")
    assert resolved.status_code == 200, resolved.text
    assert forecast_id in resolved.json()["resolved_forecast_ids"]

    calibration = client.get(f"/v1/horizon/users/{uid}/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["mean_predictive_lead_time_hours"] == 48.0

    detections = client.get("/v1/horizon/materialization/detections?limit=500")
    assert detections.status_code == 200
    own = [item for item in detections.json() if item["forecast_id"] == forecast_id]
    assert len(own) == 1
    detection = own[0]
    assert detection["predictive_lead_time_hours"] == 48.0
    assert strong["id"] in detection["evidence_signal_ids"]
    assert detection["rule"]["probability"] is False
    assert detection["rule"]["causal_proof"] is False

    replay = _scan(forecast_id, "2020-07-06T00:00:00Z")
    assert replay.status_code == 200
    assert forecast_id not in replay.json()["resolved_forecast_ids"]


def test_two_independent_medium_sources_materialize_at_second_source_arrival():
    tag = _tag()
    _, event_id, _, forecast_id = _setup_case(tag)

    _signal(
        event_id,
        tag,
        "stockout_reports",
        "2020-07-04T12:00:00Z",
        source="medium-source-a",
        reliability=0.72,
    )
    first = _scan(forecast_id, "2020-07-04T13:00:00Z")
    assert first.status_code == 200
    assert forecast_id not in first.json()["resolved_forecast_ids"]

    _signal(
        event_id,
        tag,
        "stockout_reports",
        "2020-07-04T18:00:00Z",
        source="medium-source-b",
        reliability=0.72,
    )
    second = _scan(forecast_id, "2020-07-04T19:00:00Z")
    assert second.status_code == 200, second.text
    assert forecast_id in second.json()["resolved_forecast_ids"]

    detections = client.get("/v1/horizon/materialization/detections?limit=500")
    own = [item for item in detections.json() if item["forecast_id"] == forecast_id]
    assert len(own) == 1
    assert own[0]["predictive_lead_time_hours"] == 30.0
    assert set(own[0]["evidence_sources"]) == {"medium-source-a", "medium-source-b"}


def test_materialization_route_is_mounted():
    response = client.post(
        "/v1/horizon/materialization/scan",
        json={"mode": "live", "max_forecasts": 1},
    )
    assert response.status_code != 404
