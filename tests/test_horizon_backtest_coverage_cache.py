from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_source_schemas import HorizonSourceUpsert
from app.main import app
from app.services.horizon_coverage import HorizonHistoricalCoverageService
from app.services.horizon_sources import HorizonSourceService

client = TestClient(app)


def test_narrow_new_coverage_evidence_invalidates_cached_backtest_and_enables_negative_label():
    tag = uuid4().hex[:10]
    uid = f"coverage-cache-{tag}"
    event_type = f"coverage-cache-event-{tag}"
    precursor_type = f"coverage-cache-precursor-{tag}"
    outcome_type = f"coverage-cache-outcome-{tag}"

    user = client.put(f"/v1/users/{uid}", json={"external_id": uid})
    assert user.status_code == 200, user.text

    pattern = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"coverage-cache-pattern-{tag}",
            "name": "Coverage cache invalidation pattern",
            "event_types": [event_type],
            "required_signal_types": [precursor_type],
            "predicted_response": "A covered outcome may appear.",
            "mechanism_chain": ["event", "precursor", "outcome"],
            "expected_lag_hours_low": 12,
            "expected_lag_hours_high": 48,
            "confidence": 0.8,
            "support_count": 0,
            "contradiction_count": 0,
            "provenance": {
                "materialization_signal_types": [outcome_type],
                "forecast_expiry_grace_hours": 0,
            },
            "knowledge_available_at": "2019-01-01T00:00:00Z",
        },
    )
    assert pattern.status_code == 200, pattern.text

    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"coverage-cache-event-key-{tag}",
            "event_type": event_type,
            "title": "Coverage cache event",
            "summary": "Synthetic event.",
            "geography": ["FR"],
            "source": "synthetic-cache-source",
            "source_url": "https://example.invalid/cache",
            "source_reliability": 0.95,
            "raw_facts": {"synthetic": True},
            "occurred_at": "2020-01-01T00:00:00Z",
            "first_observed_at": "2020-01-01T00:00:00Z",
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    precursor = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"coverage-cache-precursor-key-{tag}",
            "signal_type": precursor_type,
            "source": "synthetic-cache-signal",
            "geography": ["FR"],
            "value": 1,
            "baseline": 0,
            "normalized_score": 1.0,
            "direction": "up",
            "reliability": 0.9,
            "evidence": {"synthetic": True},
            "observed_at": "2020-01-01T06:00:00Z",
        },
    )
    assert precursor.status_code == 200, precursor.text

    payload = {
        "start_at": "2020-01-01T00:00:00Z",
        "end_at": "2020-01-31T23:59:59Z",
        "evaluation_as_of": "2020-03-01T00:00:00Z",
        "event_types": [event_type],
        "max_events": 10,
        "max_cases": 10,
    }
    before = client.post(f"/v1/horizon/backtests/users/{uid}/run", json=payload)
    assert before.status_code == 200, before.text
    before_body = before.json()
    assert before_body["selected_cases"] == 0
    assert before_body["skipped"]["outcome_coverage_incomplete"] >= 1

    db = SessionLocal()
    try:
        source = HorizonSourceService(db).upsert_source(
            HorizonSourceUpsert(
                source_key=f"coverage-cache-source-{tag}",
                name=f"Coverage Cache Source {tag}",
                source_class="official_statistical",
                adapter_kind="coverage_cache_fixture",
                domains=["test"],
                geography=["FR"],
                base_locator="https://example.invalid/cache-coverage",
                trust_weight=0.9,
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
            signal_types=[outcome_type],
            geography=["FR"],
            start_at=datetime.fromisoformat("2020-01-01T06:00:00"),
            end_at=datetime.fromisoformat("2020-01-03T06:00:00"),
            completeness="complete",
            basis="narrow_decisive_coverage_fixture",
        )
    finally:
        db.close()

    after = client.post(f"/v1/horizon/backtests/users/{uid}/run", json=payload)
    assert after.status_code == 200, after.text
    after_body = after.json()
    assert after_body["run_id"] != before_body["run_id"]
    assert after_body["dataset_fingerprint"] != before_body["dataset_fingerprint"]
    assert after_body["replayed_existing_run"] is False
    assert after_body["selected_cases"] == 1
    assert after_body["outcomes"]["false"] == 1
