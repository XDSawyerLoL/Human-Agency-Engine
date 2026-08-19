from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _event(tag: str) -> int:
    response = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"cascade-event-{tag}",
            "event_type": "supply_shock",
            "title": "Synthetic supply shock",
            "summary": "Synthetic historical cascade fixture.",
            "geography": ["FR"],
            "source": "synthetic-authority",
            "source_reliability": 0.95,
            "raw_facts": {"fact_only": True},
            "occurred_at": "2020-03-01T06:00:00Z",
            "first_observed_at": "2020-03-01T06:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _pattern(tag: str) -> int:
    response = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"cascade-pattern-{tag}",
            "name": "Scarcity amplification cascade",
            "event_types": ["supply_shock"],
            "required_signal_types": ["search_interest", "purchase_velocity", "stock_availability", "queue_reports"],
            "predicted_response": "Anticipatory demand may amplify a real or perceived shortage.",
            "mechanism_chain": [
                "threat perception",
                "anticipatory search",
                "purchase acceleration",
                "inventory compression",
                "visible shortage",
            ],
            "expected_lag_hours_low": 12,
            "expected_lag_hours_high": 120,
            "confidence": 0.82,
            "support_count": 30,
            "contradiction_count": 5,
            "provenance": {
                "type": "synthetic-cascade-test",
                "stage_signal_types": {
                    "0": ["threat_mentions"],
                    "1": ["search_interest"],
                    "2": ["purchase_velocity"],
                    "3": ["stock_availability"],
                    "4": ["queue_reports"],
                },
            },
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _signal(event_id: int, tag: str, signal_type: str, stage: str, observed_at: str, score: float = 3.0):
    response = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"{signal_type}-{tag}-{uuid4().hex[:8]}",
            "signal_type": signal_type,
            "source": f"synthetic-{signal_type}",
            "geography": ["FR"],
            "value": 300,
            "baseline": 100,
            "normalized_score": score,
            "direction": "up" if score >= 0 else "down",
            "reliability": 0.95,
            "evidence": {"cascade_stage": stage, "synthetic": True},
            "observed_at": observed_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["signal_key"]


def _project(event_id: int, pattern_id: int, cutoff: str):
    response = client.post(
        "/v1/horizon/cascades/project",
        json={"event_id": event_id, "pattern_id": pattern_id, "as_of": cutoff, "mode": "backtest"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_cascade_progresses_only_through_sequentially_supported_stages():
    tag = uuid4().hex[:10]
    event_id = _event(tag)
    pattern_id = _pattern(tag)
    _signal(event_id, tag, "threat_mentions", "threat perception", "2020-03-01T08:00:00Z")
    _signal(event_id, tag, "search_interest", "anticipatory search", "2020-03-01T12:00:00Z")
    _signal(event_id, tag, "purchase_velocity", "purchase acceleration", "2020-03-01T18:00:00Z")

    body = _project(event_id, pattern_id, "2020-03-01T20:00:00Z")
    assert body["current_stage"] == "purchase acceleration"
    assert body["next_stage"] == "inventory compression"
    assert body["current_stage_index"] == 2.0
    assert body["probability_basis"] == "not_calibrated"
    assert body["interpretation"]["formal_probability_enabled"] is False
    assert [stage["state"] for stage in body["stages"][:3]] == ["established", "established", "established"]


def test_late_shortage_signal_does_not_skip_missing_middle_stage():
    tag = uuid4().hex[:10]
    event_id = _event(tag)
    pattern_id = _pattern(tag)
    _signal(event_id, tag, "threat_mentions", "threat perception", "2020-03-01T08:00:00Z")
    _signal(event_id, tag, "queue_reports", "visible shortage", "2020-03-01T10:00:00Z")

    body = _project(event_id, pattern_id, "2020-03-01T12:00:00Z")
    assert body["current_stage"] == "threat perception"
    assert body["next_stage"] == "anticipatory search"
    assert body["stages"][4]["state"] == "established"
    assert body["stages"][4]["sequentially_reached"] is False
    assert body["interpretation"]["out_of_sequence_signal_count"] == 1


def test_backtest_cutoff_never_sees_future_cascade_evidence():
    tag = uuid4().hex[:10]
    event_id = _event(tag)
    pattern_id = _pattern(tag)
    early = _signal(event_id, tag, "threat_mentions", "threat perception", "2020-03-01T08:00:00Z")
    late = _signal(event_id, tag, "search_interest", "anticipatory search", "2020-03-03T08:00:00Z")

    body = _project(event_id, pattern_id, "2020-03-02T00:00:00Z")
    serialized = str(body)
    assert early in serialized
    assert late not in serialized
    assert body["current_stage"] == "threat perception"
    assert body["next_stage"] == "anticipatory search"
