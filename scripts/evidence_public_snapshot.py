from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.db import SessionLocal
from app.services.horizon_briefing import HorizonWorldBriefingService
from app.services.human_signal_engine import HumanSignalEngine
from app.services.solution_scan import SolutionScanService


DEFAULT_OUTPUT = Path("evidence-live.json")


def _clean_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": item.get("kind"),
        "title": item.get("title"),
        "fact_status": item.get("fact_status"),
        "source": item.get("source"),
        "source_classes": list(item.get("source_classes") or []),
        "source_url": item.get("source_url"),
        "observed_at": item.get("observed_at"),
    }


def _clean_match(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ecosystem": item.get("ecosystem"),
        "title": item.get("title"),
        "url": item.get("url"),
        "published_at": item.get("published_at"),
        "relevance_score": item.get("relevance_score"),
        "relevance_score_is_probability": False,
        "matched_terms": list(item.get("matched_terms") or []),
        "is_relevant": bool(item.get("is_relevant")),
    }


def sanitize_solution_scan(scan: dict[str, Any]) -> dict[str, Any]:
    assessment = scan.get("assessment") or {}
    return {
        "status": "scanned",
        "assessment": {
            "successful_source_count": assessment.get("successful_source_count"),
            "minimum_sources_for_gap_assessment": assessment.get("minimum_sources_for_gap_assessment"),
            "coverage_sufficient_for_gap_assessment": assessment.get("coverage_sufficient_for_gap_assessment"),
            "relevant_match_count": assessment.get("relevant_match_count"),
            "ecosystems_with_relevant_matches": list(
                assessment.get("ecosystems_with_relevant_matches") or []
            ),
            "gap_status": assessment.get("gap_status"),
            "explanation": assessment.get("explanation"),
            "global_novelty_verified": False,
            "existing_solution_effectiveness_verified": False,
        },
        "sources": [
            {
                "source": source.get("source"),
                "label": source.get("label"),
                "status": source.get("status"),
                "result_count": source.get("result_count"),
            }
            for source in scan.get("sources") or []
        ],
        "matches": [
            _clean_match(item)
            for item in scan.get("matches") or []
            if item.get("is_relevant")
        ][:8],
    }


def sanitize_opportunity(
    opportunity: dict[str, Any],
    *,
    solution_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signal = opportunity.get("signal_strength") or {}
    return {
        "problem_key": opportunity.get("problem_key"),
        "domain": opportunity.get("domain"),
        "domain_label": opportunity.get("domain_label"),
        "event_type": opportunity.get("event_type"),
        "problem_statement": opportunity.get("problem_statement"),
        "signal_strength": {
            "label": signal.get("label"),
            "diagnostic_score": signal.get("diagnostic_score"),
            "diagnostic_score_is_probability": False,
            "confirmed_evidence_count": signal.get("confirmed_evidence_count"),
            "emerging_hypothesis_count": signal.get("emerging_hypothesis_count"),
            "independent_source_keys": list(signal.get("independent_source_keys") or []),
            "source_diversity_count": signal.get("source_diversity_count"),
            "persistence_hours": signal.get("persistence_hours"),
            "domain_maturity": signal.get("domain_maturity"),
            "max_corroboration_score": signal.get("max_corroboration_score"),
            "corroboration_score_is_probability": False,
        },
        "unresolvedness": {
            "status": (opportunity.get("unresolvedness") or {}).get("status"),
            "claim": (opportunity.get("unresolvedness") or {}).get("claim"),
            "solution_absence_verified": False,
        },
        "novelty": {
            "status": (opportunity.get("novelty") or {}).get("status"),
            "globally_unique_claim": False,
            "reason": (opportunity.get("novelty") or {}).get("reason"),
        },
        "candidate_action": dict(opportunity.get("candidate_action") or {}),
        "validation": dict(opportunity.get("validation") or {}),
        "evidence": [_clean_evidence(item) for item in opportunity.get("evidence") or []][:8],
        "solution_scan": (
            sanitize_solution_scan(solution_scan)
            if solution_scan is not None
            else {"status": "not_scanned_in_this_cycle"}
        ),
    }


def _local_opportunities(limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    db = SessionLocal()
    try:
        briefing = HorizonWorldBriefingService(db).snapshot(
            external_id=None,
            event_limit=200,
            candidate_limit=200,
            forecast_limit=1,
        )
        result = HumanSignalEngine().analyze(briefing, limit=limit)
        return result, list(result.get("opportunities") or [])
    finally:
        db.close()


def _remote_opportunities(
    engine_url: str,
    api_key: str,
    limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(
            f"{engine_url.rstrip('/')}/v1/horizon/world/human-signals/opportunities",
            params={"limit": limit, "event_limit": 200, "candidate_limit": 200},
            headers={"X-API-Key": api_key},
        )
        response.raise_for_status()
        result = response.json()
        return result, list(result.get("opportunities") or [])


def _remote_scan(engine_url: str, api_key: str, problem_key: str) -> dict[str, Any]:
    with httpx.Client(timeout=40, follow_redirects=True) as client:
        response = client.get(
            f"{engine_url.rstrip('/')}/v1/horizon/world/human-signals/solution-scan",
            params={"problem_key": problem_key, "max_results_per_source": 8},
            headers={"X-API-Key": api_key},
        )
        response.raise_for_status()
        return response.json()


def build_snapshot(
    *,
    opportunity_limit: int = 10,
    solution_scan_top: int = 3,
    engine_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    remote = bool(engine_url and api_key)
    if remote:
        result, opportunities = _remote_opportunities(engine_url or "", api_key or "", opportunity_limit)
    else:
        result, opportunities = _local_opportunities(opportunity_limit)

    public_opportunities: list[dict[str, Any]] = []
    scan_service = SolutionScanService(timeout_seconds=8.0) if not remote else None
    scans_attempted = 0

    for index, opportunity in enumerate(opportunities):
        scan: dict[str, Any] | None = None
        should_scan = index < max(0, solution_scan_top)
        if should_scan and opportunity.get("problem_key"):
            scans_attempted += 1
            try:
                if remote:
                    scan = _remote_scan(
                        engine_url or "",
                        api_key or "",
                        str(opportunity["problem_key"]),
                    )
                else:
                    scan = scan_service.scan(  # type: ignore[union-attr]
                        opportunity,
                        max_results_per_source=8,
                    )
            except Exception:
                scan = None
        public_opportunities.append(
            sanitize_opportunity(opportunity, solution_scan=scan)
        )

    summary = dict(result.get("summary") or {})
    return {
        "schema": "evidence-public-snapshot-v1",
        "engine": "evidence-human-signal-public-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": "remote-horizon" if remote else "github-only-horizon",
        "status": "live",
        "summary": {
            "evidence_items_considered": summary.get("evidence_items_considered", 0),
            "opportunities_returned": len(public_opportunities),
            "strong_signals": summary.get("strong_signals", 0),
            "emerging_signals": summary.get("emerging_signals", 0),
            "solution_scans_attempted": scans_attempted,
            "diagnostic_scores_are_probabilities": False,
            "solution_absence_verified": False,
            "novelty_verified": False,
        },
        "opportunities": public_opportunities,
        "critical_semantics": {
            "public_world_evidence_only": True,
            "personal_data_included": False,
            "api_key_included": False,
            "diagnostic_score_is_probability": False,
            "anomaly_index_is_probability": False,
            "no_match_means_global_novelty": False,
            "solution_scan_scope_is_limited": True,
            "human_validation_required_before_build": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a sanitized Évidence snapshot")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--opportunity-limit", type=int, default=10)
    parser.add_argument("--solution-scan-top", type=int, default=3)
    args = parser.parse_args()

    output = Path(args.output)
    engine_url = os.getenv("ENGINE_URL") or None
    api_key = os.getenv("ENGINE_API_KEY") or None
    snapshot = build_snapshot(
        opportunity_limit=max(1, min(args.opportunity_limit, 20)),
        solution_scan_top=max(0, min(args.solution_scan_top, 5)),
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
                "opportunities": len(snapshot["opportunities"]),
                "scans": snapshot["summary"]["solution_scans_attempted"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
