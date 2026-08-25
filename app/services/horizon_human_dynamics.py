from __future__ import annotations

from math import exp, log
from statistics import mean, pstdev
from typing import Any

from ..horizon_human_dynamics_schemas import (
    BehaviorOption,
    HumanDynamicsComparisonRequest,
    HumanDynamicsRequest,
)


DEFAULT_MECHANISM_WEIGHTS = {
    "incentive": 0.30,
    "habit": 0.25,
    "social": 0.25,
    "stress": 0.20,
}


def _center(value: float) -> float:
    return (value - 0.5) * 2.0


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(value, 0.0) for value in values.values())
    if total <= 0.0:
        equal = 1.0 / max(len(values), 1)
        return {key: equal for key in values}
    return {key: max(value, 0.0) / total for key, value in values.items()}


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    ceiling = max(scores.values())
    exps = {key: exp(value - ceiling) for key, value in scores.items()}
    return _normalize(exps)


def _entropy(probabilities: dict[str, float]) -> float:
    if len(probabilities) <= 1:
        return 0.0
    raw = -sum(value * log(value) for value in probabilities.values() if value > 0.0)
    return raw / log(len(probabilities))


def _mechanism_scores(option: BehaviorOption) -> dict[str, float]:
    prior = log(max(option.base_rate, 1e-9))
    return {
        "incentive": (
            prior
            + 1.60 * _center(option.perceived_benefit)
            - 1.35 * _center(option.friction)
            + 0.80 * _center(option.perceived_control)
            + 0.35 * _center(option.evidence_salience)
        ),
        "habit": (
            prior
            + 1.85 * _center(option.habit_strength)
            + 0.85 * _center(option.identity_alignment)
            - 0.60 * _center(option.friction)
            + 0.25 * _center(option.norm_support)
        ),
        "social": (
            prior
            + 1.75 * _center(option.norm_support)
            + 1.45 * _center(option.network_exposure)
            + 0.55 * _center(option.identity_alignment)
            + 0.35 * _center(option.evidence_salience)
        ),
        "stress": (
            prior
            + 1.70 * _center(option.urgency)
            + 1.20 * _center(option.threat_reduction)
            + 0.75 * _center(option.perceived_control)
            - 0.70 * _center(option.friction)
            + 0.35 * _center(option.evidence_salience)
        ),
    }


def _normalized_weights(request: HumanDynamicsRequest) -> dict[str, float]:
    weights = dict(DEFAULT_MECHANISM_WEIGHTS)
    if request.mechanism_weights is not None:
        for name in weights:
            if name in request.mechanism_weights:
                weights[name] = request.mechanism_weights[name]
    return _normalize(weights)


def _timing(option: BehaviorOption, horizon_hours: float) -> dict[str, Any]:
    speed = (
        0.34 * option.urgency
        + 0.22 * option.network_exposure
        + 0.18 * option.evidence_salience
        + 0.16 * option.threat_reduction
        + 0.10 * option.perceived_control
    )
    friction_drag = 0.45 + 0.55 * option.friction
    if option.typical_latency_hours is not None:
        base = min(option.typical_latency_hours, horizon_hours)
        median_hours = base * friction_drag / max(0.35 + speed, 0.1)
    else:
        median_hours = horizon_hours * friction_drag / max(1.0 + 2.5 * speed, 1.0)
    median_hours = min(max(median_hours, 0.1), horizon_hours)
    ratio = median_hours / horizon_hours
    if ratio <= 0.12:
        label = "immediate"
    elif ratio <= 0.40:
        label = "near_term"
    elif ratio <= 0.75:
        label = "mid_horizon"
    else:
        label = "late_horizon"
    return {
        "label": label,
        "median_hours_if_action_occurs": round(median_hours, 2),
        "method": "behavioral_timing_heuristic",
        "empirically_calibrated": False,
    }


def _drivers(option: BehaviorOption) -> list[dict[str, Any]]:
    dimensions = {
        "perceived_benefit": option.perceived_benefit,
        "low_friction": 1.0 - option.friction,
        "norm_support": option.norm_support,
        "identity_alignment": option.identity_alignment,
        "habit_strength": option.habit_strength,
        "network_exposure": option.network_exposure,
        "urgency": option.urgency,
        "threat_reduction": option.threat_reduction,
        "perceived_control": option.perceived_control,
        "evidence_salience": option.evidence_salience,
    }
    ranked = sorted(
        dimensions.items(),
        key=lambda item: abs(item[1] - 0.5),
        reverse=True,
    )[:4]
    return [
        {
            "factor": name,
            "value": round(value, 4),
            "direction": "supports" if value >= 0.5 else "weakens",
        }
        for name, value in ranked
    ]


class HumanDynamicsEngine:
    ENGINE_VERSION = "horizon-human-dynamics-v1.0"

    def predict(self, request: HumanDynamicsRequest) -> dict[str, Any]:
        options = {option.key: option for option in request.options}
        weights = _normalized_weights(request)

        scores_by_mechanism: dict[str, dict[str, float]] = {
            name: {} for name in DEFAULT_MECHANISM_WEIGHTS
        }
        for option in request.options:
            scores = _mechanism_scores(option)
            for mechanism, score in scores.items():
                scores_by_mechanism[mechanism][option.key] = score

        probabilities_by_mechanism = {
            mechanism: _softmax(scores)
            for mechanism, scores in scores_by_mechanism.items()
        }

        pooled = {
            action_key: sum(
                weights[mechanism] * probabilities_by_mechanism[mechanism][action_key]
                for mechanism in weights
            )
            for action_key in options
        }
        pooled = _normalize(pooled)

        evidence_updates: list[dict[str, Any]] = []
        for observation in request.observations:
            before = dict(pooled)
            updated = {}
            for action_key, probability in pooled.items():
                likelihood_ratio = observation.likelihood_by_action.get(action_key, 1.0)
                adjusted_lr = likelihood_ratio ** observation.reliability
                updated[action_key] = probability * adjusted_lr
            pooled = _normalize(updated)
            evidence_updates.append(
                {
                    "signal": observation.signal,
                    "reliability": observation.reliability,
                    "likelihood_by_action": observation.likelihood_by_action,
                    "probability_shift": {
                        key: round(pooled[key] - before[key], 6)
                        for key in pooled
                    },
                }
            )

        model_spread = {}
        for action_key in options:
            values = [
                probabilities_by_mechanism[name][action_key]
                for name in probabilities_by_mechanism
            ]
            model_spread[action_key] = pstdev(values) if len(values) > 1 else 0.0

        entropy = _entropy(pooled)
        mean_disagreement = mean(model_spread.values()) if model_spread else 0.0
        evidence_component = request.evidence_quality
        observation_component = (
            mean(observation.reliability for observation in request.observations)
            if request.observations
            else 0.5
        )
        confidence_score = max(
            0.0,
            min(
                1.0,
                0.55 * evidence_component
                + 0.20 * observation_component
                + 0.15 * (1.0 - entropy)
                + 0.10 * (1.0 - min(mean_disagreement * 4.0, 1.0)),
            ),
        )
        if confidence_score >= 0.75:
            confidence_label = "strong_model_confidence"
        elif confidence_score >= 0.50:
            confidence_label = "moderate_model_confidence"
        else:
            confidence_label = "weak_model_confidence"

        actions = []
        for action_key, probability in pooled.items():
            option = options[action_key]
            uncertainty = (
                0.06
                + 0.20 * (1.0 - request.evidence_quality)
                + 0.40 * min(model_spread[action_key], 0.30)
            )
            actions.append(
                {
                    "key": action_key,
                    "label": option.label,
                    "probability": round(probability, 6),
                    "plausibility_band": {
                        "low": round(max(0.0, probability - uncertainty), 6),
                        "high": round(min(1.0, probability + uncertainty), 6),
                        "statistical_confidence_interval": False,
                    },
                    "timing": _timing(option, request.horizon_hours),
                    "drivers": _drivers(option),
                    "model_disagreement": round(model_spread[action_key], 6),
                    "mechanism_probabilities": {
                        mechanism: round(
                            probabilities_by_mechanism[mechanism][action_key], 6
                        )
                        for mechanism in probabilities_by_mechanism
                    },
                }
            )
        actions.sort(key=lambda row: row["probability"], reverse=True)

        return {
            "engine": self.ENGINE_VERSION,
            "scenario_id": request.scenario_id,
            "scenario": request.scenario,
            "population": request.population,
            "horizon_hours": request.horizon_hours,
            "prediction_status": "uncalibrated_model_estimate",
            "empirically_calibrated": False,
            "probabilities_are_observed_frequencies": False,
            "mechanism_weights": {key: round(value, 6) for key, value in weights.items()},
            "confidence": {
                "label": confidence_label,
                "score": round(confidence_score, 6),
                "evidence_quality": request.evidence_quality,
                "normalized_entropy": round(entropy, 6),
                "mean_mechanism_disagreement": round(mean_disagreement, 6),
                "confidence_is_empirical_accuracy": False,
            },
            "leading_action": actions[0] if actions else None,
            "actions": actions,
            "evidence_updates": evidence_updates,
            "critical_semantics": {
                "probability_is_model_estimate": True,
                "plausibility_band_is_statistical_confidence_interval": False,
                "timing_is_empirically_calibrated": False,
                "individual_outcome_is_deterministic": False,
                "use_for_high_stakes_individual_decisions_without_validation": False,
            },
        }

    def compare(self, request: HumanDynamicsComparisonRequest) -> dict[str, Any]:
        baseline = self.predict(request.baseline)
        baseline_probabilities = {
            action["key"]: action["probability"] for action in baseline["actions"]
        }
        counterfactuals = []
        for counterfactual_request in request.counterfactuals:
            result = self.predict(counterfactual_request)
            deltas = []
            for action in result["actions"]:
                key = action["key"]
                if key not in baseline_probabilities:
                    continue
                deltas.append(
                    {
                        "key": key,
                        "label": action["label"],
                        "baseline_probability": baseline_probabilities[key],
                        "counterfactual_probability": action["probability"],
                        "delta": round(
                            action["probability"] - baseline_probabilities[key], 6
                        ),
                    }
                )
            deltas.sort(key=lambda row: abs(row["delta"]), reverse=True)
            counterfactuals.append(
                {
                    "scenario_id": counterfactual_request.scenario_id,
                    "scenario": counterfactual_request.scenario,
                    "leading_action": result["leading_action"],
                    "action_deltas": deltas,
                    "full_prediction": result,
                }
            )
        return {
            "engine": self.ENGINE_VERSION,
            "comparison_type": "counterfactual_sensitivity_analysis",
            "baseline": baseline,
            "counterfactuals": counterfactuals,
            "critical_semantics": {
                "counterfactual_is_causal_effect_estimate": False,
                "comparison_requires_domain_validation": True,
            },
        }
