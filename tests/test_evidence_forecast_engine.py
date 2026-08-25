from datetime import datetime, timedelta, timezone

from app.services.evidence_forecast_engine import EvidenceForecastEngine


def _candidate(
    *,
    candidate_id: int,
    title: str,
    corroboration: float,
    source_classes: list[str],
    first: str,
    last: str,
    pattern_confidence: float,
) -> dict:
    return {
        "kind": "emerging_hypothesis",
        "id": candidate_id,
        "event_type": "rail_transport_disruption",
        "title": title,
        "domain": "transport_mobility",
        "domain_label": "Transport & mobilité",
        "fact_status": "unconfirmed_emerging_event",
        "source_classes": source_classes,
        "corroboration_score": corroboration,
        "first_observed_at": first,
        "observed_at": last,
        "provisional_forecasts": [
            {
                "forecast_id": candidate_id * 10,
                "pattern_key": f"pattern-{candidate_id}",
                "pattern_name": "Transport cascade",
                "predicted_response": "hausse mesurable des perturbations et reports de mobilité",
                "mechanism_chain": [
                    "pression opérationnelle",
                    "réduction de capacité",
                    "reports de mobilité",
                ],
                "pattern_confidence": pattern_confidence,
                "hypothesis_band": "watch",
                "provisional_score": corroboration,
                "provisional_score_is_probability": False,
                "relative_lag_hours": {"low": 12, "high": 48},
                "fact_status": "unconfirmed_emerging_event",
                "user_surface_allowed": False,
            }
        ],
    }


def _confirmed_event(*, event_id: int, occurred_at: str, high_hours: int = 48) -> dict:
    return {
        "kind": "confirmed_event",
        "id": event_id,
        "event_type": "rail_transport_disruption",
        "title": "Perturbation ferroviaire confirmée",
        "domain": "transport_mobility",
        "domain_label": "Transport & mobilité",
        "fact_status": "confirmed_or_derived_event",
        "source": "sncf",
        "source_reliability": 0.91,
        "observed_at": occurred_at,
        "occurred_at": occurred_at,
        "predictive_patterns": [
            {
                "pattern_key": "confirmed-transport-cascade",
                "pattern_name": "Transport cascade",
                "predicted_response": "hausse de la congestion routière et des reports vers des modes alternatifs",
                "mechanism_chain": [
                    "perte de capacité ferroviaire",
                    "substitution de mode",
                    "pression sur le réseau routier",
                ],
                "pattern_confidence": 0.72,
                "relative_lag_hours": {"low": 0, "high": high_hours},
                "support_count": 0,
                "contradiction_count": 0,
                "formal_probability": False,
                "calibrated_on_horizon_outcomes": False,
            }
        ],
    }


def test_evidence_forecast_engine_ranks_stronger_convergence_higher():
    briefing = {
        "engine": "test-briefing",
        "events": [],
        "hypotheses": [
            _candidate(
                candidate_id=1,
                title="Strong transport precursor",
                corroboration=0.84,
                source_classes=["transport", "world_events", "media"],
                first="2026-08-20T08:00:00+00:00",
                last="2026-08-24T08:00:00+00:00",
                pattern_confidence=0.82,
            ),
            _candidate(
                candidate_id=2,
                title="Weak transport precursor",
                corroboration=0.35,
                source_classes=["media"],
                first="2026-08-24T06:00:00+00:00",
                last="2026-08-24T08:00:00+00:00",
                pattern_confidence=0.45,
            ),
        ],
    }
    graph = {
        "nodes": [
            {"key": "event:10", "title": "Upstream network pressure", "event_type": "network_pressure"},
            {"key": "candidate:1", "title": "Strong transport precursor", "event_type": "rail_transport_disruption"},
            {"key": "candidate:2", "title": "Weak transport precursor", "event_type": "rail_transport_disruption"},
        ],
        "edges": [
            {
                "left": "event:10",
                "right": "candidate:1",
                "relation": "plausible_downstream_dependency",
                "diagnostic_score": 0.86,
                "evidence": {"mechanism_rule": "pressure->transport"},
            }
        ],
    }

    result = EvidenceForecastEngine().forecast(briefing, graph=graph, limit=10)

    assert len(result["forecasts"]) == 2
    strong, weak = result["forecasts"]
    assert strong["candidate_id"] == 1
    assert strong["probability"]["estimate"] > weak["probability"]["estimate"]
    assert 0.05 <= weak["probability"]["estimate"] <= 0.92
    assert 0.05 <= strong["probability"]["estimate"] <= 0.92


def test_evidence_forecast_marks_model_estimate_as_uncalibrated():
    briefing = {
        "engine": "test-briefing",
        "events": [],
        "hypotheses": [
            _candidate(
                candidate_id=3,
                title="Emerging signal",
                corroboration=0.72,
                source_classes=["transport", "world_events"],
                first="2026-08-22T08:00:00+00:00",
                last="2026-08-24T08:00:00+00:00",
                pattern_confidence=0.76,
            )
        ],
    }

    forecast = EvidenceForecastEngine().forecast(briefing, graph={}, limit=5)["forecasts"][0]
    probability = forecast["probability"]

    assert probability["type"] == "model_estimate"
    assert probability["empirically_calibrated"] is False
    assert probability["can_be_read_as_empirical_frequency"] is False
    assert probability["calibration_status"] == "uncalibrated_model_estimate"
    assert probability["interval_low"] <= probability["estimate"] <= probability["interval_high"]


def test_unconfirmed_candidate_keeps_relative_window_and_falsification():
    briefing = {
        "engine": "test-briefing",
        "events": [],
        "hypotheses": [
            _candidate(
                candidate_id=4,
                title="Unconfirmed precursor",
                corroboration=0.65,
                source_classes=["transport", "media"],
                first="2026-08-23T08:00:00+00:00",
                last="2026-08-24T08:00:00+00:00",
                pattern_confidence=0.70,
            )
        ],
    }

    forecast = EvidenceForecastEngine().forecast(briefing, graph={}, limit=5)["forecasts"][0]

    assert forecast["fact_status"] == "forecast_from_unconfirmed_emerging_signal"
    assert forecast["time_window"]["kind"] == "relative_after_precursor_confirmation"
    assert forecast["time_window"]["absolute_dates_claimed"] is False
    assert forecast["time_window"]["low_hours"] == 12
    assert forecast["time_window"]["high_hours"] == 48
    assert forecast["falsification"]
    assert forecast["probability_up_if"]
    assert forecast["probability_down_if"]


def test_graph_dependency_is_exposed_as_driver_not_causal_proof():
    briefing = {
        "engine": "test-briefing",
        "events": [],
        "hypotheses": [
            _candidate(
                candidate_id=5,
                title="Target candidate",
                corroboration=0.68,
                source_classes=["transport", "world_events"],
                first="2026-08-23T08:00:00+00:00",
                last="2026-08-24T08:00:00+00:00",
                pattern_confidence=0.72,
            )
        ],
    }
    graph = {
        "nodes": [
            {"key": "event:20", "title": "Precursor event", "event_type": "upstream_pressure"},
            {"key": "candidate:5", "title": "Target candidate", "event_type": "rail_transport_disruption"},
        ],
        "edges": [
            {
                "left": "event:20",
                "right": "candidate:5",
                "relation": "plausible_downstream_dependency",
                "diagnostic_score": 0.79,
                "evidence": {"causal_claim": False},
            }
        ],
    }

    forecast = EvidenceForecastEngine().forecast(briefing, graph=graph, limit=5)["forecasts"][0]
    precursor = next(driver for driver in forecast["drivers"] if driver["type"] == "precursor_dependency")

    assert precursor["label"] == "Precursor event"
    assert precursor["causal_proof"] is False
    assert precursor["support_score_is_probability"] is False
    assert forecast["model_components"]["graph_dependency_support"] == 0.79


def test_confirmed_event_continues_prediction_with_absolute_window():
    occurred_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    briefing = {
        "engine": "test-briefing",
        "events": [_confirmed_event(event_id=30, occurred_at=occurred_at)],
        "hypotheses": [],
    }

    result = EvidenceForecastEngine().forecast(briefing, graph={}, limit=5)
    forecast = result["forecasts"][0]

    assert forecast["event_id"] == 30
    assert forecast["candidate_id"] is None
    assert forecast["fact_status"] == "forecast_from_confirmed_event"
    assert forecast["time_window"]["kind"] == "absolute_after_confirmed_precursor"
    assert forecast["time_window"]["absolute_dates_claimed"] is True
    assert forecast["time_window"]["expired"] is False
    assert forecast["model_components"]["precursor_confirmed"] is True
    assert forecast["probability"]["empirically_calibrated"] is False
    assert result["summary"]["confirmed_precursor_predictions"] == 1


def test_expired_confirmed_event_is_not_published_as_active_prediction():
    occurred_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    briefing = {
        "engine": "test-briefing",
        "events": [_confirmed_event(event_id=31, occurred_at=occurred_at, high_hours=24)],
        "hypotheses": [],
    }

    result = EvidenceForecastEngine().forecast(briefing, graph={}, limit=5)

    assert result["forecasts"] == []
    assert result["summary"]["predictions_returned"] == 0
    assert result["critical_semantics"]["expired_confirmed_scenarios_are_published_as_active"] is False
