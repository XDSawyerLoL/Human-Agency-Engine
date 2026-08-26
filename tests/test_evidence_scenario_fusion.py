from __future__ import annotations

from app.services.evidence_scenario_fusion import EvidenceScenarioFusion


def _forecast(*, event_id: int, probability: int = 44, source: str = "sncf-service-alerts") -> dict:
    return {
        "scenario_key": f"raw-{event_id}",
        "candidate_id": None,
        "event_id": event_id,
        "domain": "transport_mobility",
        "domain_label": "Transport & mobility",
        "event_type": "rail_transport_disruption",
        "headline": "A substantial public-transport disruption can push travelers toward substitute modes.",
        "outcome": "A substantial public-transport disruption can push travelers toward substitute modes.",
        "fact_status": "forecast_from_confirmed_event",
        "trajectory": "forming",
        "probability": {
            "estimate": probability / 100,
            "percent": probability,
            "interval_percent": [26, 63],
            "evidence_quality": 0.61,
        },
        "time_window": {
            "kind": "absolute_after_confirmed_precursor",
            "start_at": "2026-08-26T06:00:00Z",
            "end_at": "2026-08-27T06:00:00Z",
            "human": "du 26/08 06:00 au 27/08 06:00 UTC",
        },
        "drivers": [{
            "type": "confirmed_precursor",
            "label": f"raw alert {event_id}",
            "event_type": "rail_transport_disruption",
            "source_classes": [source],
            "support_score": 0.93,
        }],
        "evidence": [{
            "kind": "confirmed_event",
            "title": f"raw alert {event_id}",
            "source_classes": [source],
            "observed_at": "2026-08-26T07:00:00Z",
        }],
        "model_components": {
            "precursor_confirmed": True,
            "source_reliability": 0.93,
            "source_diversity": 1,
            "pattern_confidence": 0.56,
            "graph_dependency_support": 0.0,
        },
    }


def test_duplicate_event_forecasts_collapse_to_one_public_scenario():
    result = EvidenceScenarioFusion().fuse([_forecast(event_id=1), _forecast(event_id=2)], limit=10)
    assert len(result) == 1
    fused = result[0]
    assert fused["fusion"]["raw_forecast_count"] == 2
    assert fused["fusion"]["supporting_event_ids"] == [1, 2]
    assert fused["fusion"]["duplicate_probability_inflation_prevented"] is True


def test_duplicate_rows_do_not_raise_probability():
    result = EvidenceScenarioFusion().fuse(
        [_forecast(event_id=1, probability=44), _forecast(event_id=2, probability=44)],
        limit=10,
    )
    assert result[0]["probability"]["percent"] == 44
    assert result[0]["fusion"]["probability_recomputed_after_fusion"] is False


def test_strongest_existing_forecast_is_representative_without_weighted_merge():
    result = EvidenceScenarioFusion().fuse(
        [_forecast(event_id=1, probability=41), _forecast(event_id=2, probability=47)],
        limit=10,
    )
    assert result[0]["probability"]["percent"] == 47
    assert result[0]["fusion"]["probability_merge_method"] == "strongest_representative_not_recomputed"


def test_public_rail_scenario_is_french_and_hides_raw_forecast_wording():
    result = EvidenceScenarioFusion().fuse([_forecast(event_id=1)], limit=10)
    fused = result[0]
    assert fused["public_language"] == "fr"
    assert "Perturbation ferroviaire" in fused["headline"]
    assert "public-transport" not in fused["headline"]
    assert "capacité ferroviaire réduite" in fused["causal_chain"]


def test_support_from_two_source_keys_is_visible_but_does_not_recompute_probability():
    result = EvidenceScenarioFusion().fuse(
        [_forecast(event_id=1, source="sncf-service-alerts"), _forecast(event_id=2, source="gdelt-news-global")],
        limit=10,
    )
    fused = result[0]
    assert fused["fusion"]["source_keys"] == ["gdelt-news-global", "sncf-service-alerts"]
    assert fused["model_components"]["source_diversity"] == 2
    assert fused["probability"]["percent"] == 44
