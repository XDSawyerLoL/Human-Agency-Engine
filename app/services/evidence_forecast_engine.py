from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import exp, log1p
from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def _scenario_key(entity_key: Any, pattern_key: str, outcome: str) -> str:
    raw = f"{entity_key}|{pattern_key}|{outcome}".encode("utf-8")
    return sha256(raw).hexdigest()[:24]


def _hours_between(first: Any, last: Any) -> float:
    start = _parse_dt(first)
    end = _parse_dt(last)
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 3600.0)


def _human_duration_window(low: Any, high: Any, *, reference: str = "confirmation du précurseur") -> str:
    try:
        low_h = max(0.0, float(low))
        high_h = max(low_h, float(high))
    except (TypeError, ValueError):
        return "fenêtre temporelle encore indéterminée"

    def unit(hours: float) -> str:
        if hours >= 24 * 14:
            return f"{hours / (24 * 7):.0f} sem."
        if hours >= 48:
            return f"{hours / 24:.0f} j"
        return f"{hours:.0f} h"

    if abs(high_h - low_h) < 0.01:
        return f"environ {unit(low_h)} après {reference}"
    return f"{unit(low_h)} à {unit(high_h)} après {reference}"


def _absolute_window(occurred_at: Any, low: Any, high: Any) -> dict[str, Any] | None:
    start = _parse_dt(occurred_at)
    if start is None:
        return None
    try:
        low_h = max(0.0, float(low))
        high_h = max(low_h, float(high))
    except (TypeError, ValueError):
        return None
    low_dt = start + timedelta(hours=low_h)
    high_dt = start + timedelta(hours=high_h)
    return {
        "kind": "absolute_after_confirmed_precursor",
        "low_hours": low_h,
        "high_hours": high_h,
        "start_at": low_dt.isoformat() + "Z",
        "end_at": high_dt.isoformat() + "Z",
        "human": (
            f"du {low_dt.strftime('%d/%m %H:%M')} au {high_dt.strftime('%d/%m %H:%M')} UTC"
            if low_dt != high_dt
            else f"autour du {low_dt.strftime('%d/%m %H:%M')} UTC"
        ),
        "absolute_dates_claimed": True,
        "expired": high_dt < _utc_now(),
    }


def _trajectory(corroboration: float, diversity: float, persistence: float, graph_support: float) -> str:
    if corroboration >= 0.68 and diversity >= 0.66 and (persistence >= 0.45 or graph_support >= 0.72):
        return "building"
    if corroboration >= 0.48 and (diversity >= 0.33 or graph_support >= 0.55):
        return "forming"
    return "fragile"


class EvidenceForecastEngine:
    """Turn HORIZON signals and confirmed precursors into falsifiable future scenarios.

    Percentages emitted by this engine are model estimates, not observed frequencies.
    They may only be relabelled as empirically calibrated probabilities after a
    separate HORIZON historical calibration gate has passed.
    """

    ENGINE_VERSION = "evidence-predictive-scenarios-v0.2"
    PROBABILITY_METHOD = "evidence-log-odds-v0.2"

    @staticmethod
    def _graph_indexes(graph: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        graph = graph or {}
        nodes = {
            str(item.get("key")): item
            for item in graph.get("nodes") or []
            if item.get("key")
        }
        incoming: dict[str, list[dict[str, Any]]] = {}
        for edge in graph.get("edges") or []:
            if edge.get("relation") != "plausible_downstream_dependency":
                continue
            right = str(edge.get("right") or "")
            if not right:
                continue
            incoming.setdefault(right, []).append(edge)
        return nodes, incoming

    @staticmethod
    def _drivers_for_node(
        node_key: str,
        nodes: dict[str, dict[str, Any]],
        incoming: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], float]:
        drivers: list[dict[str, Any]] = []
        support = 0.0
        for edge in sorted(
            incoming.get(node_key, []),
            key=lambda item: float(item.get("diagnostic_score") or 0.0),
            reverse=True,
        )[:5]:
            left = nodes.get(str(edge.get("left") or ""), {})
            score = _clamp(float(edge.get("diagnostic_score") or 0.0))
            support = max(support, score)
            drivers.append({
                "type": "precursor_dependency",
                "label": left.get("title") or left.get("event_type") or edge.get("left"),
                "event_type": left.get("event_type"),
                "support_score": round(score, 4),
                "support_score_is_probability": False,
                "relation": edge.get("relation"),
                "causal_proof": False,
                "evidence": dict(edge.get("evidence") or {}),
            })
        return drivers, support

    @classmethod
    def _model_probability(
        cls,
        *,
        corroboration: float,
        source_diversity: int,
        persistence_hours: float,
        pattern_confidence: float,
        graph_support: float,
        confirmed_precursor: bool = False,
    ) -> dict[str, Any]:
        c = _clamp(corroboration)
        d = _clamp(source_diversity / 3.0)
        p = _clamp(log1p(max(0.0, persistence_hours)) / log1p(168.0))
        pattern = _clamp(pattern_confidence if pattern_confidence > 0 else 0.5)
        graph = _clamp(graph_support if graph_support > 0 else 0.5)

        # Conservative prior: most weak-signal scenarios do not materialize.
        log_odds = -1.10
        log_odds += 1.90 * (c - 0.5)
        log_odds += 1.15 * (d - 0.5)
        log_odds += 0.85 * (p - 0.5)
        log_odds += 1.35 * (pattern - 0.5)
        log_odds += 1.05 * (graph - 0.5)
        if confirmed_precursor:
            # Confirmation removes uncertainty about the precursor, not about the outcome.
            log_odds += 0.45
        estimate = _clamp(_sigmoid(log_odds), 0.05, 0.92)

        evidence_quality = _clamp(
            0.34 * c
            + 0.20 * d
            + 0.14 * p
            + 0.16 * pattern
            + 0.10 * graph
            + (0.06 if confirmed_precursor else 0.0)
        )
        half_width = 0.28 - 0.16 * evidence_quality
        low = _clamp(estimate - half_width, 0.01, 0.99)
        high = _clamp(estimate + half_width, 0.01, 0.99)

        return {
            "type": "model_estimate",
            "estimate": round(estimate, 4),
            "percent": round(estimate * 100),
            "interval_low": round(low, 4),
            "interval_mid": round(estimate, 4),
            "interval_high": round(high, 4),
            "interval_percent": [round(low * 100), round(high * 100)],
            "method": cls.PROBABILITY_METHOD,
            "calibration_status": "uncalibrated_model_estimate",
            "empirically_calibrated": False,
            "can_be_read_as_empirical_frequency": False,
            "evidence_quality": round(evidence_quality, 4),
        }

    @staticmethod
    def _why_now_emerging(
        *,
        title: str,
        outcome: str,
        corroboration: float,
        source_diversity: int,
        persistence_hours: float,
        drivers: list[dict[str, Any]],
    ) -> str:
        pieces = [
            f"« {title} » est actuellement traité comme un signal émergent, pas comme un fait acquis.",
            f"Il est soutenu par {source_diversity} famille{'s' if source_diversity != 1 else ''} de sources avec un niveau de corroboration de {round(corroboration * 100)}/100.",
        ]
        if persistence_hours >= 1:
            pieces.append(f"Le signal reste observable depuis environ {round(persistence_hours)} h.")
        if drivers:
            pieces.append(
                f"HORIZON relie aussi {len(drivers)} précurseur{'s' if len(drivers) != 1 else ''} plausible{'s' if len(drivers) != 1 else ''} à cette trajectoire."
            )
        pieces.append(f"Si cette combinaison continue de se renforcer, le scénario projeté est : {outcome}.")
        return " ".join(pieces)

    @staticmethod
    def _why_now_confirmed(
        *,
        title: str,
        outcome: str,
        source: str,
        reliability: float,
        drivers: list[dict[str, Any]],
    ) -> str:
        pieces = [
            f"Le précurseur « {title} » est désormais enregistré comme événement confirmé ou dérivé par HORIZON.",
            f"Sa source principale est {source or 'non précisée'} avec une fiabilité déclarée de {round(reliability * 100)}/100.",
        ]
        if drivers:
            pieces.append(
                f"Le graphe relie {len(drivers)} événement{'s' if len(drivers) != 1 else ''} amont plausible{'s' if len(drivers) != 1 else ''} à cette situation."
            )
        pieces.append(f"Le moteur projette maintenant la conséquence suivante : {outcome}.")
        return " ".join(pieces)

    @staticmethod
    def _falsification(outcome: str, human_window: str) -> str:
        return (
            f"Le scénario est considéré comme raté si le signal observable correspondant à « {outcome} » "
            f"n'apparaît pas dans la fenêtre déclarée ({human_window}), ou si les observations indépendantes "
            "contredisent la trajectoire avant l'échéance."
        )

    def _forecast_emerging(
        self,
        candidate: dict[str, Any],
        *,
        nodes: dict[str, dict[str, Any]],
        incoming: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        scenarios: list[dict[str, Any]] = []
        candidate_id = candidate.get("id")
        title = str(candidate.get("title") or candidate.get("event_type") or "Signal émergent")
        corroboration = _clamp(float(candidate.get("corroboration_score") or 0.0))
        source_classes = sorted({str(item) for item in (candidate.get("source_classes") or []) if item})
        persistence_hours = _hours_between(candidate.get("first_observed_at"), candidate.get("observed_at"))
        graph_drivers, graph_support = self._drivers_for_node(f"candidate:{candidate_id}", nodes, incoming)

        candidate_driver = {
            "type": "emerging_signal",
            "label": title,
            "event_type": candidate.get("event_type"),
            "support_score": round(corroboration, 4),
            "support_score_is_probability": False,
            "source_classes": source_classes,
            "first_observed_at": candidate.get("first_observed_at"),
            "last_observed_at": candidate.get("observed_at"),
            "fact_status": candidate.get("fact_status"),
        }

        for provisional in candidate.get("provisional_forecasts") or []:
            outcome = str(provisional.get("predicted_response") or "").strip()
            if not outcome:
                continue
            pattern_key = str(provisional.get("pattern_key") or "unknown-pattern")
            pattern_confidence = _clamp(float(provisional.get("pattern_confidence") or 0.5))
            lag = provisional.get("relative_lag_hours") or {}
            low_h = lag.get("low")
            high_h = lag.get("high")
            human_window = _human_duration_window(low_h, high_h)
            mechanism_chain = [str(item) for item in (provisional.get("mechanism_chain") or []) if str(item).strip()]
            probability = self._model_probability(
                corroboration=corroboration,
                source_diversity=len(source_classes),
                persistence_hours=persistence_hours,
                pattern_confidence=pattern_confidence,
                graph_support=graph_support,
            )
            trajectory = _trajectory(
                corroboration,
                _clamp(len(source_classes) / 3.0),
                _clamp(log1p(max(0.0, persistence_hours)) / log1p(168.0)),
                graph_support,
            )
            next_stage = mechanism_chain[0] if mechanism_chain else outcome

            scenarios.append({
                "scenario_key": _scenario_key(f"candidate:{candidate_id}", pattern_key, outcome),
                "candidate_id": candidate_id,
                "event_id": None,
                "domain": candidate.get("domain"),
                "domain_label": candidate.get("domain_label") or candidate.get("domain"),
                "event_type": candidate.get("event_type"),
                "headline": outcome,
                "outcome": outcome,
                "fact_status": "forecast_from_unconfirmed_emerging_signal",
                "trajectory": trajectory,
                "probability": probability,
                "time_window": {
                    "kind": "relative_after_precursor_confirmation",
                    "low_hours": low_h,
                    "high_hours": high_h,
                    "human": human_window,
                    "absolute_dates_claimed": False,
                    "expired": False,
                },
                "why_now": self._why_now_emerging(
                    title=title,
                    outcome=outcome,
                    corroboration=corroboration,
                    source_diversity=len(source_classes),
                    persistence_hours=persistence_hours,
                    drivers=graph_drivers,
                ),
                "causal_chain": mechanism_chain or [title, outcome],
                "drivers": [candidate_driver, *graph_drivers],
                "watch_next": [
                    next_stage,
                    "promotion du signal émergent en événement confirmé",
                    "nouvelle corroboration provenant d'une famille de sources indépendante",
                ],
                "probability_up_if": [
                    "une nouvelle famille de sources indépendante confirme le même signal",
                    "le candidat émergent est promu en événement confirmé par HORIZON",
                    f"un signal correspondant à l'étape suivante apparaît : {next_stage}",
                ],
                "probability_down_if": [
                    "aucune nouvelle observation indépendante n'arrive alors que le signal vieillit",
                    "la corroboration multi-sources recule ou une source clé est invalidée",
                    f"la fenêtre prévue expire sans matérialisation observable de : {outcome}",
                ],
                "falsification": self._falsification(outcome, human_window),
                "evidence": [{
                    "kind": candidate.get("kind"),
                    "title": title,
                    "fact_status": candidate.get("fact_status"),
                    "source_classes": source_classes,
                    "observed_at": candidate.get("observed_at"),
                    "first_observed_at": candidate.get("first_observed_at"),
                    "corroboration_score": round(corroboration, 4),
                    "corroboration_score_is_probability": False,
                }],
                "model_components": {
                    "precursor_confirmed": False,
                    "corroboration": round(corroboration, 4),
                    "source_diversity": len(source_classes),
                    "persistence_hours": round(persistence_hours, 2),
                    "pattern_confidence": round(pattern_confidence, 4),
                    "graph_dependency_support": round(graph_support, 4),
                    "component_scores_are_probabilities": False,
                },
            })
        return scenarios

    def _forecast_confirmed_event(
        self,
        event: dict[str, Any],
        *,
        nodes: dict[str, dict[str, Any]],
        incoming: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        scenarios: list[dict[str, Any]] = []
        event_id = event.get("id")
        title = str(event.get("title") or event.get("event_type") or "Événement confirmé")
        reliability = _clamp(float(event.get("source_reliability") or 0.5))
        source = str(event.get("source") or "")
        graph_drivers, graph_support = self._drivers_for_node(f"event:{event_id}", nodes, incoming)
        persistence_hours = _hours_between(event.get("occurred_at"), event.get("observed_at"))
        source_classes = [source] if source else []
        confirmed_driver = {
            "type": "confirmed_precursor",
            "label": title,
            "event_type": event.get("event_type"),
            "support_score": round(reliability, 4),
            "support_score_is_probability": False,
            "source_classes": source_classes,
            "first_observed_at": event.get("observed_at"),
            "last_observed_at": event.get("observed_at"),
            "fact_status": event.get("fact_status"),
        }

        for pattern in event.get("predictive_patterns") or []:
            outcome = str(pattern.get("predicted_response") or "").strip()
            if not outcome:
                continue
            lag = pattern.get("relative_lag_hours") or {}
            window = _absolute_window(event.get("occurred_at"), lag.get("low"), lag.get("high"))
            if window is None or window.get("expired"):
                continue
            pattern_key = str(pattern.get("pattern_key") or "unknown-pattern")
            pattern_confidence = _clamp(float(pattern.get("pattern_confidence") or 0.5))
            mechanism_chain = [str(item) for item in (pattern.get("mechanism_chain") or []) if str(item).strip()]
            probability = self._model_probability(
                corroboration=reliability,
                source_diversity=max(1, len(source_classes)),
                persistence_hours=persistence_hours,
                pattern_confidence=pattern_confidence,
                graph_support=graph_support,
                confirmed_precursor=True,
            )
            next_stage = mechanism_chain[0] if mechanism_chain else outcome
            trajectory = "building" if probability["estimate"] >= 0.60 else "forming"

            scenarios.append({
                "scenario_key": _scenario_key(f"event:{event_id}", pattern_key, outcome),
                "candidate_id": None,
                "event_id": event_id,
                "domain": event.get("domain"),
                "domain_label": event.get("domain_label") or event.get("domain"),
                "event_type": event.get("event_type"),
                "headline": outcome,
                "outcome": outcome,
                "fact_status": "forecast_from_confirmed_event",
                "trajectory": trajectory,
                "probability": probability,
                "time_window": window,
                "why_now": self._why_now_confirmed(
                    title=title,
                    outcome=outcome,
                    source=source,
                    reliability=reliability,
                    drivers=graph_drivers,
                ),
                "causal_chain": mechanism_chain or [title, outcome],
                "drivers": [confirmed_driver, *graph_drivers],
                "watch_next": [
                    next_stage,
                    "signal observable correspondant à une étape intermédiaire du mécanisme",
                    "matérialisation indépendante du résultat projeté",
                ],
                "probability_up_if": [
                    f"un signal correspondant à l'étape suivante apparaît : {next_stage}",
                    "une source indépendante confirme une conséquence intermédiaire du mécanisme",
                    "le graphe HORIZON ajoute un précurseur amont cohérent dans la même zone et fenêtre temporelle",
                ],
                "probability_down_if": [
                    "les indicateurs intermédiaires attendus restent absents",
                    "des observations indépendantes montrent que la pression se résorbe",
                    f"la fenêtre expire sans matérialisation observable de : {outcome}",
                ],
                "falsification": self._falsification(outcome, str(window.get("human") or "fenêtre déclarée")),
                "evidence": [{
                    "kind": event.get("kind"),
                    "title": title,
                    "fact_status": event.get("fact_status"),
                    "source_classes": source_classes,
                    "observed_at": event.get("observed_at"),
                    "first_observed_at": event.get("observed_at"),
                    "corroboration_score": round(reliability, 4),
                    "corroboration_score_is_probability": False,
                }],
                "model_components": {
                    "precursor_confirmed": True,
                    "source_reliability": round(reliability, 4),
                    "source_diversity": max(1, len(source_classes)),
                    "persistence_hours": round(persistence_hours, 2),
                    "pattern_confidence": round(pattern_confidence, 4),
                    "graph_dependency_support": round(graph_support, 4),
                    "pattern_support_count": int(pattern.get("support_count") or 0),
                    "pattern_contradiction_count": int(pattern.get("contradiction_count") or 0),
                    "pattern_empirically_calibrated": bool(pattern.get("calibrated_on_horizon_outcomes")),
                    "component_scores_are_probabilities": False,
                },
            })
        return scenarios

    def forecast(
        self,
        briefing: dict[str, Any],
        *,
        graph: dict[str, Any] | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        nodes, incoming = self._graph_indexes(graph)
        hypotheses = list(briefing.get("hypotheses") or [])
        events = list(briefing.get("events") or [])
        scenarios: list[dict[str, Any]] = []

        for candidate in hypotheses:
            scenarios.extend(self._forecast_emerging(candidate, nodes=nodes, incoming=incoming))
        for event in events:
            scenarios.extend(self._forecast_confirmed_event(event, nodes=nodes, incoming=incoming))

        scenarios.sort(
            key=lambda item: (
                float((item.get("probability") or {}).get("estimate") or 0.0),
                float((item.get("probability") or {}).get("evidence_quality") or 0.0),
            ),
            reverse=True,
        )
        scenarios = scenarios[: max(1, min(int(limit), 100))]
        confirmed_count = sum(1 for item in scenarios if item.get("fact_status") == "forecast_from_confirmed_event")
        emerging_count = len(scenarios) - confirmed_count

        return {
            "engine": self.ENGINE_VERSION,
            "generated_from": briefing.get("engine"),
            "summary": {
                "evidence_items_considered": len(events) + len(hypotheses),
                "confirmed_events_considered": len(events),
                "emerging_signals_considered": len(hypotheses),
                "predictions_returned": len(scenarios),
                "confirmed_precursor_predictions": confirmed_count,
                "emerging_precursor_predictions": emerging_count,
                "model_probability_estimates": len(scenarios),
                "empirically_calibrated_predictions": 0,
                "dependency_edges_considered": sum(len(value) for value in incoming.values()),
                "numeric_model_estimates_enabled": True,
                "empirical_probability_calibration_enabled": False,
            },
            "forecasts": scenarios,
            "critical_semantics": {
                "model_estimate_is_certainty": False,
                "model_estimate_is_empirical_frequency": False,
                "unconfirmed_candidates_remain_unconfirmed": True,
                "confirmed_precursor_confirms_outcome": False,
                "graph_dependency_is_causal_proof": False,
                "forecast_windows_are_time_bounded": True,
                "expired_confirmed_scenarios_are_published_as_active": False,
                "every_forecast_has_falsification_rule": True,
                "historical_calibration_required_for_empirical_probability_claim": True,
            },
        }
