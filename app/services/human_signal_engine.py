from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


MATURITY_BONUS = {
    "missing": 0,
    "source_only": 2,
    "discovery_only": 4,
    "live_single_source": 7,
    "live_multi_source": 10,
    "historically_calibratable": 12,
    "personalized": 8,
}

ACTION_ARCHETYPES = {
    "weather_climate": (
        "local exposure and action-timing assistant",
        "Turn verified weather signals into a location-aware decision and a clear action window.",
    ),
    "natural_hazards": (
        "local exposure and continuity assistant",
        "Combine verified hazard signals with exposure, fallback routes and a time-bounded action plan.",
    ),
    "transport_mobility": (
        "mobility continuity assistant",
        "Aggregate disruption evidence, estimate practical exposure and propose verified fallback options.",
    ),
    "social_collective_behavior": (
        "collective-friction early warning tool",
        "Track converging social signals and translate them into operational preparation instead of raw alerts.",
    ),
    "supply_fuel": (
        "availability and fallback planner",
        "Detect recurring supply friction early and turn it into stock, timing or alternative-source decisions.",
    ),
    "energy": (
        "energy continuity planner",
        "Translate supply or grid stress into concrete continuity, timing and cost decisions.",
    ),
    "media_attention": (
        "signal verification and coordination tool",
        "Separate repeated attention from independent evidence, then surface only decisions supported by convergence.",
    ),
    "geopolitics_security": (
        "exposure and continuity cockpit",
        "Connect verified geopolitical changes to concrete operational exposure and contingency decisions.",
    ),
    "economy_labor": (
        "economic-friction scenario planner",
        "Translate verified labor or corporate stress into short-horizon scenarios and measurable next actions.",
    ),
    "public_health": (
        "early advisory and response assistant",
        "Convert independently corroborated health signals into practical guidance with explicit uncertainty.",
    ),
    "cyber_technology": (
        "service continuity and recovery assistant",
        "Detect independently corroborated outages or incidents and trigger a verified recovery workflow.",
    ),
    "regulation_policy": (
        "policy impact translator",
        "Convert verified regulatory change into affected-user impacts, deadlines and a concrete compliance path.",
    ),
    "financial_stress": (
        "financial resilience early-warning tool",
        "Turn verified stress signals into exposure checks, contingency thresholds and measurable mitigation steps.",
    ),
    "personal_context": (
        "personal relevance layer",
        "Connect external evidence to explicit user constraints without turning inferred preferences into facts.",
    ),
}

DEFAULT_ACTION = (
    "evidence-to-action assistant",
    "Turn independently supported signals into one concrete decision, explicit assumptions and a measurable test.",
)


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _source_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    source = item.get("source")
    if source:
        keys.add(str(source))
    for source_class in item.get("source_classes") or []:
        if source_class:
            keys.add(str(source_class))
    return keys


def _evidence_reference(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": item.get("kind"),
        "id": item.get("id"),
        "title": item.get("title") or item.get("event_title"),
        "fact_status": item.get("fact_status"),
        "source": item.get("source"),
        "source_classes": item.get("source_classes") or [],
        "source_url": item.get("source_url"),
        "observed_at": item.get("observed_at") or item.get("as_of"),
    }


def _diagnostic_label(score: int) -> str:
    if score >= 70:
        return "strong_signal"
    if score >= 45:
        return "emerging_signal"
    return "weak_signal"


def _validation_test(domain: str, event_type: str, sample_size: int) -> dict[str, Any]:
    episode_count = max(3, min(10, sample_size + 2))
    return {
        "hypothesis": (
            f"People exposed to repeated {event_type.replace('_', ' ')} signals have a recurring decision "
            "or coordination friction that existing responses do not remove reliably."
        ),
        "fast_test": (
            "For the next observed episodes, record the decision users had to make, the time lost, the workaround "
            "used and whether an existing tool already solved the problem end-to-end."
        ),
        "reject_if": (
            f"Reject the opportunity if {episode_count} comparable episodes show no repeated friction, "
            "or if affected users consistently solve it with an existing response without meaningful delay or loss."
        ),
        "domain": domain,
        "episode_target": episode_count,
    }


class HumanSignalEngine:
    """Convert HORIZON evidence into explicit unresolved-problem hypotheses.

    This layer is deliberately diagnostic. It does not claim novelty, solution absence
    or market demand without a separate solution scan and user validation.
    """

    ENGINE_VERSION = "evidence-human-signal-v0.1"

    def analyze(self, briefing: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        rows.extend(briefing.get("events") or [])
        rows.extend(briefing.get("hypotheses") or [])

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in rows:
            domain = str(item.get("domain") or "unknown")
            event_type = str(item.get("event_type") or "unknown")
            grouped[(domain, event_type)].append(item)

        opportunities: list[dict[str, Any]] = []
        for (domain, event_type), items in grouped.items():
            confirmed = [item for item in items if item.get("kind") == "confirmed_event"]
            hypotheses = [item for item in items if item.get("kind") == "emerging_hypothesis"]
            source_keys = set().union(*(_source_keys(item) for item in items)) if items else set()

            timestamps = []
            for item in items:
                for key in ("first_observed_at", "observed_at", "occurred_at"):
                    parsed = _parse_dt(item.get(key))
                    if parsed is not None:
                        timestamps.append(parsed)
            persistence_hours = 0.0
            if len(timestamps) >= 2:
                try:
                    persistence_hours = max(
                        0.0,
                        (max(timestamps) - min(timestamps)).total_seconds() / 3600.0,
                    )
                except TypeError:
                    persistence_hours = 0.0

            maturity = next(
                (str(item.get("maturity")) for item in items if item.get("maturity")),
                "missing",
            )
            corroboration_values = [
                float(item.get("corroboration_score"))
                for item in hypotheses
                if item.get("corroboration_score") is not None
            ]
            max_corroboration = max(corroboration_values, default=0.0)

            persistence_bonus = 0
            if persistence_hours >= 168:
                persistence_bonus = 12
            elif persistence_hours >= 72:
                persistence_bonus = 9
            elif persistence_hours >= 24:
                persistence_bonus = 6
            elif persistence_hours >= 6:
                persistence_bonus = 3

            diagnostic_score = min(
                100,
                len(confirmed) * 22
                + min(len(hypotheses), 5) * 8
                + min(len(source_keys), 5) * 7
                + persistence_bonus
                + MATURITY_BONUS.get(maturity, 0)
                + (5 if max_corroboration >= 0.7 else 2 if max_corroboration >= 0.4 else 0),
            )

            representative = max(
                items,
                key=lambda item: (
                    item.get("kind") == "confirmed_event",
                    item.get("observed_at") or item.get("first_observed_at") or "",
                ),
            )
            representative_title = (
                representative.get("title")
                or representative.get("event_title")
                or event_type.replace("_", " ").title()
            )
            tool_name, tool_mechanism = ACTION_ARCHETYPES.get(domain, DEFAULT_ACTION)

            evidence = [_evidence_reference(item) for item in items[:8]]
            opportunity = {
                "problem_key": f"{domain}:{event_type}",
                "domain": domain,
                "domain_label": representative.get("domain_label") or domain,
                "event_type": event_type,
                "problem_statement": (
                    f"Repeated or independently supported signals around ‘{representative_title}’ may indicate "
                    "a recurring human decision, coordination or access problem worth testing."
                ),
                "signal_strength": {
                    "label": _diagnostic_label(diagnostic_score),
                    "diagnostic_score": diagnostic_score,
                    "diagnostic_score_is_probability": False,
                    "confirmed_evidence_count": len(confirmed),
                    "emerging_hypothesis_count": len(hypotheses),
                    "independent_source_keys": sorted(source_keys),
                    "source_diversity_count": len(source_keys),
                    "persistence_hours": round(persistence_hours, 1),
                    "domain_maturity": maturity,
                    "max_corroboration_score": round(max_corroboration, 4),
                    "corroboration_score_is_probability": False,
                },
                "unresolvedness": {
                    "status": "needs_solution_scan",
                    "claim": (
                        "The engine has evidence of the underlying signal, but it has not yet established that "
                        "existing solutions fail or that the problem is globally unresolved."
                    ),
                    "solution_absence_verified": False,
                },
                "novelty": {
                    "status": "not_assessed",
                    "globally_unique_claim": False,
                    "reason": (
                        "Novelty requires a separate scan of products, public services, research, patents and "
                        "community work; absence cannot be inferred from the news or event stream."
                    ),
                },
                "candidate_action": {
                    "type": "tool_or_workflow_experiment",
                    "tool_archetype": tool_name,
                    "mechanism": tool_mechanism,
                    "first_build": (
                        f"Prototype a narrow {tool_name} for the {event_type.replace('_', ' ')} case. "
                        "It must consume verified HORIZON evidence, expose uncertainty, and produce one measurable "
                        "next action rather than another feed of alerts."
                    ),
                },
                "validation": _validation_test(domain, event_type, len(items)),
                "evidence": evidence,
            }
            opportunities.append(opportunity)

        opportunities.sort(
            key=lambda item: (
                item["signal_strength"]["diagnostic_score"],
                item["signal_strength"]["confirmed_evidence_count"],
                item["signal_strength"]["source_diversity_count"],
            ),
            reverse=True,
        )
        opportunities = opportunities[: max(1, min(limit, 100))]

        strong = sum(
            item["signal_strength"]["label"] == "strong_signal"
            for item in opportunities
        )
        emerging = sum(
            item["signal_strength"]["label"] == "emerging_signal"
            for item in opportunities
        )

        return {
            "engine": self.ENGINE_VERSION,
            "generated_from": briefing.get("engine"),
            "summary": {
                "evidence_items_considered": len(rows),
                "opportunities_returned": len(opportunities),
                "strong_signals": strong,
                "emerging_signals": emerging,
                "diagnostic_scores_are_probabilities": False,
                "solution_absence_verified": False,
                "novelty_verified": False,
            },
            "opportunities": opportunities,
            "critical_semantics": {
                "problem_signal_is_proof_of_unresolved_problem": False,
                "solution_absence_requires_external_scan": True,
                "novelty_requires_external_scan": True,
                "diagnostic_score_is_probability": False,
                "human_validation_required_before_build": True,
            },
        }
