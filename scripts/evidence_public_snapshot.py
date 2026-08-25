from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.db import SessionLocal
from app.horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from app.services.evidence_forecast_engine import EvidenceForecastEngine
from app.services.horizon_briefing import HorizonWorldBriefingService
from app.services.horizon_event_graph import HorizonEventGraphService


DEFAULT_OUTPUT = Path("evidence-live.json")


def _clean_driver(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": item.get("type"),
        "label": item.get("label"),
        "event_type": item.get("event_type"),
        "support_score": item.get("support_score"),
        "support_score_is_probability": False,
        "relation": item.get("relation"),
        "causal_proof": False if item.get("type") == "precursor_dependency" else item.get("causal_proof"),
        "source_classes": list(item.get("source_classes") or []),
        "fact_status": item.get("fact_status"),
        "first_observed_at": item.get("first_observed_at"),
        "last_observed_at": item.get("last_observed_at"),
    }


def _clean_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": item.get("kind"),
        "title": item.get("title"),
        "fact_status": item.get("fact_status"),
        "source_classes": list(item.get("source_classes") or []),
        "observed_at": item.get("observed_at"),
        "first_observed_at": item.get("first_observed_at"),
        "corroboration_score": item.get("corroboration_score"),
        "corroboration_score_is_probability": False,
    }


def sanitize_forecast(item: dict[str, Any]) -> dict[str, Any]:
    probability = dict(item.get("probability") or {})
    return {
        "scenario_key": item.get("scenario_key"),
        "candidate_id": item.get("candidate_id"),
        "domain": item.get("domain"),
        "domain_label": item.get("domain_label"),
        "event_type": item.get("event_type"),
        "headline": item.get("headline"),
        "outcome": item.get("outcome"),
        "fact_status": item.get("fact_status"),
        "trajectory": item.get("trajectory"),
        "probability": {
            "type": probability.get("type"),
            "estimate": probability.get("estimate"),
            "percent": probability.get("percent"),
            "interval_low": probability.get("interval_low"),
            "interval_mid": probability.get("interval_mid"),
            "interval_high": probability.get("interval_high"),
            "interval_percent": list(probability.get("interval_percent") or []),
            "method": probability.get("method"),
            "calibration_status": probability.get("calibration_status"),
            "empirically_calibrated": bool(probability.get("empirically_calibrated")),
            "can_be_read_as_empirical_frequency": False,
            "evidence_quality": probability.get("evidence_quality"),
        },
        "time_window": dict(item.get("time_window") or {}),
        "why_now": item.get("why_now"),
        "causal_chain": list(item.get("causal_chain") or []),
        "drivers": [_clean_driver(driver) for driver in item.get("drivers") or []][:8],
        "watch_next": list(item.get("watch_next") or [])[:6],
        "probability_up_if": list(item.get("probability_up_if") or [])[:6],
        "probability_down_if": list(item.get("probability_down_if") or [])[:6],
        "falsification": item.get("falsification"),
        "evidence": [_clean_evidence(evidence) for evidence in item.get("evidence") or []][:8],
        "model_components": dict(item.get("model_components") or {}),
    }


def _local_forecasts(limit: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        briefing = HorizonWorldBriefingService(db).snapshot(
            external_id=None,
            event_limit=200,
            candidate_limit=200,
            forecast_limit=1,
        )
        graph_result = HorizonEventGraphService(db).build(
            HorizonEventGraphBuildRequest(
                lookback_hours=336,
                max_events=200,
                max_candidates=200,
                max_signals=1200,
            )
        )
        return EvidenceForecastEngine().forecast(
            briefing,
            graph=graph_result.get("graph_snapshot") or {},
            limit=limit,
        )
    finally:
        db.close()


def _remote_forecasts(engine_url: str, api_key: str, limit: int) -> dict[str, Any]:
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        response = client.get(
            f"{engine_url.rstrip('/')}/v1/horizon/world/human-signals/forecasts",
            params={
                "limit": limit,
                "event_limit": 200,
                "candidate_limit": 200,
                "lookback_hours": 336,
            },
            headers={"X-API-Key": api_key},
        )
        response.raise_for_status()
        return response.json()


def build_snapshot(
    *,
    forecast_limit: int = 10,
    engine_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    remote = bool(engine_url and api_key)
    if remote:
        result = _remote_forecasts(engine_url or "", api_key or "", forecast_limit)
    else:
        result = _local_forecasts(forecast_limit)

    public_forecasts = [
        sanitize_forecast(item)
        for item in result.get("forecasts") or []
    ]
    summary = dict(result.get("summary") or {})
    source_families = {
        source
        for forecast in public_forecasts
        for driver in forecast.get("drivers") or []
        for source in driver.get("source_classes") or []
    }

    return {
        "schema": "evidence-public-snapshot-v2",
        "engine": "evidence-predictive-public-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": "remote-horizon" if remote else "github-only-horizon",
        "status": "live",
        "summary": {
            "evidence_items_considered": summary.get("evidence_items_considered", 0),
            "emerging_signals_considered": summary.get("emerging_signals_considered", 0),
            "predictions_returned": len(public_forecasts),
            "model_probability_estimates": summary.get("model_probability_estimates", len(public_forecasts)),
            "empirically_calibrated_predictions": summary.get("empirically_calibrated_predictions", 0),
            "dependency_edges_considered": summary.get("dependency_edges_considered", 0),
            "source_families": len(source_families),
            "numeric_model_estimates_enabled": True,
            "empirical_probability_calibration_enabled": False,
        },
        "forecasts": public_forecasts,
        "critical_semantics": {
            "public_world_evidence_only": True,
            "personal_data_included": False,
            "api_key_included": False,
            "model_probability_is_certainty": False,
            "model_probability_is_empirical_frequency": False,
            "empirical_probability_calibration_enabled": False,
            "unconfirmed_candidates_remain_unconfirmed": True,
            "dependency_edge_is_causal_proof": False,
            "forecasts_are_time_bounded": True,
            "every_forecast_has_falsification_rule": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a sanitized predictive Évidence snapshot")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--forecast-limit", type=int, default=None)
    # Legacy flags remain accepted so older workflow invocations do not break mid-deploy.
    parser.add_argument("--opportunity-limit", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--solution-scan-top", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    requested_limit = args.forecast_limit or args.opportunity_limit or 10
    output = Path(args.output)
    engine_url = os.getenv("ENGINE_URL") or None
    api_key = os.getenv("ENGINE_API_KEY") or None
    snapshot = build_snapshot(
        forecast_limit=max(1, min(requested_limit, 20)),
        engine_url=engine_url,
        api_key=api_key,
    )
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": snapshot["status"],
                "runtime_mode": snapshot["runtime_mode"],
                "forecasts": len(snapshot["forecasts"]),
                "calibrated": snapshot["summary"]["empirically_calibrated_predictions"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
