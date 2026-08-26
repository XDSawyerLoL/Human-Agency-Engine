from __future__ import annotations

from datetime import datetime, timezone

from app.services.evidence_consolidation import EvidenceConsolidator, MODEL_PRIOR_PERCENT


def _forecast(*, confirmed: bool = False, sources: list[str] | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "headline": "Perturbation régionale probable",
        "probability": {
            "percent": 68,
            "interval_percent": [51, 80],
            "calibration_status": "uncalibrated_model_estimate",
        },
        "drivers": [
            {
                "type": "confirmed_precursor" if confirmed else "emerging_signal",
                "source_classes": sources or ["news_global"],
                "last_observed_at": now,
            }
        ],
        "model_components": {
            "precursor_confirmed": confirmed,
            "source_diversity": len(sources or ["news_global"]),
            "pattern_confidence": 0.78,
            "graph_dependency_support": 0.72,
            "source_reliability": 0.92 if confirmed else None,
            "corroboration": 0.68,
        },
    }


def test_consolidation_score_is_explicitly_not_probability():
    result = EvidenceConsolidator().consolidate(_forecast())
    assert 0 <= result["score"] <= 100
    assert result["score_is_probability"] is False
    assert "ne sont pas eux-mêmes des probabilités" in result["probability_case"]["explanation"]


def test_multi_family_sources_increase_diversity_dimension():
    consolidator = EvidenceConsolidator()
    one = consolidator.consolidate(_forecast(sources=["news_global"]))
    many = consolidator.consolidate(
        _forecast(sources=["news_global", "model_forecast", "official_statistical"])
    )
    one_diversity = next(item for item in one["dimensions"] if item["key"] == "source_diversity")
    many_diversity = next(item for item in many["dimensions"] if item["key"] == "source_diversity")
    assert many_diversity["score"] > one_diversity["score"]
    assert many["source_family_count"] == 3


def test_confirmed_precursor_adds_visible_strength():
    result = EvidenceConsolidator().consolidate(
        _forecast(confirmed=True, sources=["official_primary", "news_global"])
    )
    assert any("confirmé" in item.lower() for item in result["strengths"])


def test_binary_scenario_competition_is_mutually_exclusive_and_sums_to_100():
    result = EvidenceConsolidator().consolidate(_forecast())
    competition = result["scenario_competition"]
    assert competition["mutually_exclusive"] is True
    assert sum(item["percent"] for item in competition["outcomes"]) == 100


def test_default_divergence_uses_internal_prior_not_fake_external_consensus():
    result = EvidenceConsolidator().consolidate(_forecast())
    divergence = result["divergence"]
    assert divergence["reference_type"] == "internal_model_prior"
    assert divergence["reference_percent"] == MODEL_PRIOR_PERCENT
    assert divergence["external_consensus_available"] is False


def test_authorized_external_consensus_is_used_when_explicitly_supplied():
    forecast = _forecast()
    forecast["consensus_reference"] = {
        "authorized": True,
        "type": "licensed_human_forecast",
        "label": "Consensus autorisé",
        "percent": 55,
    }
    result = EvidenceConsolidator().consolidate(forecast)
    divergence = result["divergence"]
    assert divergence["reference_type"] == "licensed_human_forecast"
    assert divergence["reference_percent"] == 55
    assert divergence["external_consensus_available"] is True
    assert divergence["delta_points"] == 13
