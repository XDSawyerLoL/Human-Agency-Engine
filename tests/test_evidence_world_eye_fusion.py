from __future__ import annotations

from app.services.evidence_scenario_fusion import EvidenceScenarioFusion


def _forecast(event_id: int, *, event_type: str, label: str, probability: int = 50) -> dict:
    return {
        "scenario_key": f"raw-{event_id}",
        "candidate_id": None,
        "event_id": event_id,
        "domain": "world",
        "domain_label": "World",
        "event_type": event_type,
        "headline": f"future outcome {event_type}",
        "outcome": f"future outcome {event_type}",
        "fact_status": "forecast_from_confirmed_event",
        "trajectory": "forming",
        "probability": {
            "estimate": probability / 100,
            "percent": probability,
            "interval_percent": [30, 70],
            "evidence_quality": 0.60,
        },
        "time_window": {
            "kind": "absolute_after_confirmed_precursor",
            "start_at": "2026-08-26T06:00:00Z",
            "end_at": "2026-08-27T06:00:00Z",
            "human": "du 26/08 06:00 au 27/08 06:00 UTC",
        },
        "drivers": [{
            "type": "confirmed_precursor",
            "label": label,
            "event_type": event_type,
            "source_classes": ["fixture-source"],
        }],
        "evidence": [],
        "model_components": {"source_diversity": 1},
    }


def test_fuel_rows_same_department_collapse_but_different_departments_survive():
    forecasts = [
        _forecast(1, event_type="fuel_supply_disruption", label="Ruptures temporaires de SP98 — département 95 (19/103)"),
        _forecast(2, event_type="fuel_supply_disruption", label="Ruptures temporaires de SP95 — département 95 (17/103)"),
        _forecast(3, event_type="fuel_supply_disruption", label="Ruptures temporaires de Gazole — département 13 (25/120)"),
    ]
    result = EvidenceScenarioFusion().fuse(forecasts, limit=20)
    assert len(result) == 2
    counts = sorted(item["fusion"]["raw_forecast_count"] for item in result)
    assert counts == [1, 2]
    assert all(item["fusion"]["geography_aware_grouping"] is True for item in result)


def test_distinct_earthquake_places_remain_distinct_scenarios():
    result = EvidenceScenarioFusion().fuse([
        _forecast(10, event_type="major_earthquake", label="Séisme M5.8 — south of the Fiji Islands"),
        _forecast(11, event_type="major_earthquake", label="Séisme M5.9 — Vanuatu region"),
    ], limit=20)
    assert len(result) == 2


def test_distinct_health_outbreak_titles_remain_distinct_scenarios():
    result = EvidenceScenarioFusion().fuse([
        _forecast(20, event_type="disease_outbreak_signal", label="Disease outbreak A — Country A"),
        _forecast(21, event_type="disease_outbreak_signal", label="Disease outbreak B — Country B"),
    ], limit=20)
    assert len(result) == 2


def test_one_event_type_cannot_monopolize_twenty_slot_world_eye():
    fuel = [
        _forecast(100 + index, event_type="fuel_supply_disruption", label=f"Ruptures temporaires — département {index + 10}", probability=70 - index)
        for index in range(12)
    ]
    others = [
        _forecast(300, event_type="major_earthquake", label="Séisme M5.7 — Region X", probability=49),
        _forecast(301, event_type="disease_outbreak_signal", label="Outbreak Y — Region Y", probability=48),
        _forecast(302, event_type="financial_stress", label="VIX stress", probability=47),
    ]
    result = EvidenceScenarioFusion().fuse([*fuel, *others], limit=20)
    fuel_count = sum(item["event_type"] == "fuel_supply_disruption" for item in result)
    assert fuel_count == 5
    assert {item["event_type"] for item in result} >= {"major_earthquake", "disease_outbreak_signal", "financial_stress"}
