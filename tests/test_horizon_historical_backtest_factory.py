from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_source_schemas import HorizonSourceUpsert
from app.main import app
from app.services.horizon_coverage import HorizonHistoricalCoverageService
from app.services.horizon_sources import HorizonSourceService

client = TestClient(app)


def _create_user(uid: str) -> None:
    response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert response.status_code == 200, response.text


def _create_event(event_key: str, event_type: str, occurred_at: str) -> int:
    response = client.post(
        "/v1/horizon/events",
        json={
            "event_key": event_key,
            "event_type": event_type,
            "title": f"Synthetic historical event {event_key}",
            "summary": "Synthetic event for deterministic historical factory validation.",
            "geography": ["FR"],
            "source": "synthetic-historical-source",
            "source_url": "https://example.invalid/historical",
            "source_reliability": 0.95,
            "raw_facts": {"fact_only": True},
            "occurred_at": occurred_at,
            "first_observed_at": occurred_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _add_signal(
    event_id: int,
    signal_key: str,
    signal_type: str,
    observed_at: str,
    *,
    source: str = "synthetic-signal-source",
    reliability: float = 0.9,
    score: float = 1.0,
) -> None:
    response = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": signal_key,
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


def _record_complete_signal_coverage(tag: str, event_type: str, signal_type: str) -> None:
    db = SessionLocal()
    try:
        source = HorizonSourceService(db).upsert_source(
            HorizonSourceUpsert(
                source_key=f"synthetic-coverage-{tag}",
                name=f"Synthetic Complete Coverage {tag}",
                source_class="official_statistical",
                adapter_kind="synthetic_complete_coverage",
                domains=["test"],
                geography=["FR"],
                base_locator="https://example.invalid/coverage",
                trust_weight=0.95,
                refresh_seconds=3600,
                requires_credentials=False,
                enabled=True,
                metadata_json={"test_only": True},
            )
        )
        HorizonHistoricalCoverageService(db).record_interval(
            source,
            coverage_kind="signal",
            event_types=[event_type],
            signal_types=[signal_type],
            geography=["FR"],
            start_at=datetime.fromisoformat("2020-01-01T00:00:00"),
            end_at=datetime.fromisoformat("2020-06-02T00:00:00"),
            completeness="complete",
            basis="synthetic_complete_test_stream",
            provenance={"test_only": True, "absence_is_observable": True},
        )
    finally:
        db.close()


def _create_pattern(tag: str, event_type: str, precursor_type: str, outcome_type: str) -> None:
    response = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"factory-pattern-{tag}",
            "name": "Synthetic historical factory pattern",
            "event_types": [event_type],
            "required_signal_types": [precursor_type],
            "predicted_response": "A visible synthetic outcome may materialize.",
            "mechanism_chain": ["event", "precursor", "visible outcome"],
            "expected_lag_hours_low": 12,
            "expected_lag_hours_high": 48,
            "confidence": 0.8,
            "support_count": 0,
            "contradiction_count": 0,
            "provenance": {
                "type": "synthetic-historical-factory-test",
                "materialization_signal_types": [outcome_type],
                "forecast_expiry_grace_hours": 0,
                "materialization_min_reliability": 0.65,
                "materialization_min_normalized_score": 0.5,
            },
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text


def test_historical_factory_builds_hindsight_safe_success_and_miss_cases_idempotently():
    tag = uuid4().hex[:10]
    uid = f"historical-factory-{tag}"
    event_type = f"factory_event_{tag}"
    precursor_type = f"factory_precursor_{tag}"
    outcome_type = f"factory_outcome_{tag}"
    _create_user(uid)
    _create_pattern(tag, event_type, precursor_type, outcome_type)
    _record_complete_signal_coverage(tag, event_type, outcome_type)

    success_event = _create_event(f"factory-success-{tag}", event_type, "2020-01-01T00:00:00Z")
    _add_signal(success_event, f"success-precursor-{tag}", precursor_type, "2020-01-01T06:00:00Z")
    _add_signal(
        success_event,
        f"success-outcome-{tag}",
        outcome_type,
        "2020-01-02T00:00:00Z",
        source="synthetic-strong-outcome-source",
        reliability=0.9,
    )

    miss_event = _create_event(f"factory-miss-{tag}", event_type, "2020-02-01T00:00:00Z")
    _add_signal(miss_event, f"miss-precursor-{tag}", precursor_type, "2020-02-01T06:00:00Z")

    hindsight_event = _create_event(f"factory-hindsight-{tag}", event_type, "2020-03-01T00:00:00Z")
    _add_signal(hindsight_event, f"hindsight-outcome-{tag}", outcome_type, "2020-03-01T05:00:00Z")
    _add_signal(hindsight_event, f"hindsight-precursor-{tag}", precursor_type, "2020-03-01T06:00:00Z")

    late_precursor_event = _create_event(f"factory-late-{tag}", event_type, "2020-04-01T00:00:00Z")
    _add_signal(late_precursor_event, f"late-precursor-{tag}", precursor_type, "2020-05-02T00:00:00Z")

    payload = {
        "start_at": "2020-01-01T00:00:00Z",
        "end_at": "2020-04-30T23:59:59Z",
        "evaluation_as_of": "2020-06-01T00:00:00Z",
        "event_types": [event_type],
        "max_events": 20,
        "max_cases": 20,
    }
    first = client.post(f"/v1/horizon/backtests/users/{uid}/run", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()

    assert body["engine"] == "horizon-historical-backtest-factory-v0.2"
    assert body["events_selected"] == 4
    assert body["selected_cases"] == 2
    assert body["outcomes"]["confirmed"] == 1
    assert body["outcomes"]["false"] == 1
    assert body["outcomes"]["unresolved"] == 0
    assert body["mean_predictive_lead_time_hours"] == 18.0
    assert body["skipped"]["outcome_already_obvious_at_cutoff"] >= 1
    assert body["skipped"]["event_pattern_mismatch_or_missing_precursor"] >= 1
    assert body["critical_semantics"]["future_signals_visible_to_forecast"] is False
    assert body["critical_semantics"]["outcome_already_obvious_cases_disqualified"] is True
    assert body["critical_semantics"]["complete_outcome_signal_coverage_required_for_every_scored_case"] is True
    assert body["critical_semantics"]["absence_of_signal_without_complete_coverage_counts_as_failure"] is False
    assert body["critical_semantics"]["positive_cases_bypass_coverage_gate"] is False
    assert body["critical_semantics"]["numeric_probabilities_enabled"] is False
    assert all(case["outcome_coverage"]["complete"] is True for case in body["calibration_after_run"].get("cases", [])) if body["calibration_after_run"].get("cases") else True

    calibration = body["calibration_after_run"]
    assert calibration["global_binary_evidence"]["binary_labels"] == 2
    assert calibration["global_binary_evidence"]["successes"] == 1
    assert calibration["global_binary_evidence"]["failures"] == 1
    assert calibration["weighted_precision"] == 0.5
    assert calibration["probability_calibration_enabled"] is False
    assert calibration["critical_semantics"]["automatic_expiry_label_available_at_deadline"] is True

    replay = client.post(f"/v1/horizon/backtests/users/{uid}/run", json=payload)
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["run_id"] == body["run_id"]
    assert replay_body["run_key"] == body["run_key"]
    assert replay_body["replayed_existing_run"] is True

    runs = client.get(f"/v1/horizon/backtests/users/{uid}/runs")
    assert runs.status_code == 200, runs.text
    own = [row for row in runs.json() if row["run_id"] == body["run_id"]]
    assert len(own) == 1


def test_historical_factory_rejects_positive_case_when_outcome_stream_coverage_is_missing():
    tag = uuid4().hex[:10]
    uid = f"historical-no-coverage-{tag}"
    event_type = f"factory_event_{tag}"
    precursor_type = f"factory_precursor_{tag}"
    outcome_type = f"factory_outcome_{tag}"
    _create_user(uid)
    _create_pattern(tag, event_type, precursor_type, outcome_type)

    event_id = _create_event(f"factory-positive-no-coverage-{tag}", event_type, "2020-01-01T00:00:00Z")
    _add_signal(event_id, f"positive-precursor-{tag}", precursor_type, "2020-01-01T06:00:00Z")
    _add_signal(
        event_id,
        f"positive-outcome-{tag}",
        outcome_type,
        "2020-01-02T00:00:00Z",
        source="synthetic-strong-outcome-source",
        reliability=0.9,
    )

    response = client.post(
        f"/v1/horizon/backtests/users/{uid}/run",
        json={
            "start_at": "2020-01-01T00:00:00Z",
            "end_at": "2020-01-31T23:59:59Z",
            "evaluation_as_of": "2020-03-01T00:00:00Z",
            "event_types": [event_type],
            "max_events": 10,
            "max_cases": 10,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_cases"] == 0
    assert body["outcomes"]["confirmed"] == 0
    assert body["outcomes"]["false"] == 0
    assert body["skipped"]["outcome_coverage_incomplete"] >= 1
    assert body["critical_semantics"]["positive_cases_bypass_coverage_gate"] is False
