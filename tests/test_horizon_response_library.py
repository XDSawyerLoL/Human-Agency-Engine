from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _create_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={"external_id": uid, "country": "FR", "currency": "EUR", "timezone": "Europe/Paris"},
    )
    assert response.status_code == 200, response.text


def test_builtin_human_response_library_is_versioned_idempotent_and_not_fake_calibrated():
    first = client.post("/v1/horizon/response-library/builtins/sync")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["library_version"] == "human-response-library-v0.4-mechanism-registry"
    assert body["formal_probabilities"] is False
    assert body["horizon_support_counts_are_real_labels_only"] is True
    assert len(body["patterns"]) == 5

    by_key = {item["pattern_key"]: item for item in body["patterns"]}
    heat = by_key["builtin-extreme-heat-cooling-demand-v1"]
    supply = by_key["builtin-supply-risk-precautionary-buying-v1"]
    regional_load = by_key["builtin-extreme-heat-regional-cooling-load-v1"]
    transport = by_key["builtin-transit-disruption-mode-substitution-v1"]
    cold = by_key["builtin-extreme-cold-regional-heating-load-v1"]

    for item in (heat, supply, regional_load, transport, cold):
        assert item["support_count"] == 0
        assert item["contradiction_count"] == 0
        assert item["confidence_is_probability"] is False
        assert item["provenance"]["status"] == "provisional_prior"
        assert item["provenance"]["calibrated_on_horizon_outcomes"] is False
        assert item["provenance"]["formal_probability"] is False
        assert item["provenance"]["evidence"]
        assert item["provenance"]["limitations"]

    assert heat["provenance"]["stage_signal_types"]["1"] == ["search_interest", "cooling_search_interest"]
    assert supply["provenance"]["stage_signal_types"]["1"] == ["scarcity_search", "scarcity_mentions", "queue_reports"]
    assert regional_load["event_types"] == ["extreme_heat_region"]
    assert regional_load["provenance"]["materialization_signal_types"] == ["cooling_load_pressure"]
    assert "rail_transport_disruption" in transport["event_types"]
    assert transport["provenance"]["evidence"][0]["doi"] == "10.1257/aer.104.9.2763"
    assert "road_congestion" in transport["provenance"]["stage_signal_types"]["3"]
    assert cold["event_types"] == ["extreme_cold_region"]
    assert cold["provenance"]["materialization_signal_types"] == ["heating_load_pressure"]

    second = client.post("/v1/horizon/response-library/builtins/sync")
    assert second.status_code == 200, second.text
    first_ids = {item["pattern_key"]: item["id"] for item in body["patterns"]}
    second_ids = {item["pattern_key"]: item["id"] for item in second.json()["patterns"]}
    assert second_ids == first_ids


def test_backtest_cannot_use_response_prior_before_its_public_knowledge_date():
    synced = client.post("/v1/horizon/response-library/builtins/sync")
    assert synced.status_code == 200
    supply_pattern = next(
        item for item in synced.json()["patterns"]
        if item["pattern_key"] == "builtin-supply-risk-precautionary-buying-v1"
    )

    uid = _uid("response-cutoff")
    _create_user(uid)
    tag = uuid4().hex[:10]
    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"historic-supply-{tag}",
            "event_type": "supply_disruption",
            "title": "Synthetic supply disruption",
            "summary": "Historical fixture for response-library cutoff testing.",
            "geography": ["FR"],
            "source": "synthetic-official",
            "source_url": "https://example.invalid/source",
            "source_reliability": 0.9,
            "raw_facts": {"fact_only": True},
            "occurred_at": "2021-01-01T00:00:00Z",
            "first_observed_at": "2021-01-01T00:00:00Z",
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    too_early = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2021-06-01T00:00:00Z", "mode": "backtest"},
    )
    assert too_early.status_code == 200, too_early.text
    early_ids = {item["pattern_id"] for item in too_early.json()["forecasts"]}
    assert supply_pattern["id"] not in early_ids

    available = client.post(
        f"/v1/horizon/users/{uid}/forecast",
        json={"event_id": event_id, "as_of": "2022-06-01T00:00:00Z", "mode": "backtest"},
    )
    assert available.status_code == 200, available.text
    own = [item for item in available.json()["forecasts"] if item["pattern_id"] == supply_pattern["id"]]
    assert len(own) == 1
    assert own[0]["forecast_layer"]["predictive_score_is_probability"] is False
    assert own[0]["forecast_layer"]["probability_interval"]["basis"] == "not_calibrated"


def test_heat_response_pattern_advances_only_with_live_stage_evidence():
    synced = client.post("/v1/horizon/response-library/builtins/sync")
    assert synced.status_code == 200
    heat_pattern = next(
        item for item in synced.json()["patterns"]
        if item["pattern_key"] == "builtin-extreme-heat-cooling-demand-v1"
    )

    tag = uuid4().hex[:10]
    event = client.post(
        "/v1/horizon/events",
        json={
            "event_key": f"response-heat-{tag}",
            "event_type": "extreme_heat",
            "title": "Synthetic official heat alert",
            "summary": "Heat alert fixture.",
            "geography": ["FR"],
            "source": "synthetic-official",
            "source_url": "https://example.invalid/heat",
            "source_reliability": 0.95,
            "raw_facts": {"fact_only": True},
            "occurred_at": "2026-08-19T06:00:00Z",
            "first_observed_at": "2026-08-19T06:00:00Z",
        },
    )
    assert event.status_code == 200, event.text
    event_id = event.json()["id"]

    initial = client.post(
        "/v1/horizon/cascades/project",
        json={"event_id": event_id, "pattern_id": heat_pattern["id"], "as_of": "2026-08-19T07:00:00Z", "mode": "backtest"},
    )
    assert initial.status_code == 200, initial.text
    assert initial.json()["current_stage"] == "pre-cascade / latent"

    signal = client.post(
        f"/v1/horizon/events/{event_id}/signals",
        json={
            "signal_key": f"heat-attention-{tag}",
            "signal_type": "heat_attention",
            "source": "synthetic-behavioral",
            "geography": ["FR"],
            "value": 300,
            "baseline": 100,
            "normalized_score": 3.0,
            "direction": "up",
            "reliability": 0.9,
            "evidence": {"fixture": True},
            "observed_at": "2026-08-19T08:00:00Z",
        },
    )
    assert signal.status_code == 200, signal.text

    advanced = client.post(
        "/v1/horizon/cascades/project",
        json={"event_id": event_id, "pattern_id": heat_pattern["id"], "as_of": "2026-08-19T09:00:00Z", "mode": "backtest"},
    )
    assert advanced.status_code == 200, advanced.text
    body = advanced.json()
    assert body["current_stage"] == "heat threat perception"
    assert body["next_stage"] == "cooling search acceleration"
    assert body["probability_basis"] == "not_calibrated"
