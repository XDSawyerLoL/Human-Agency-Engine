from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.horizon_human_dynamics_schemas import (
    BehaviorObservation,
    BehaviorOption,
    HumanDynamicsComparisonRequest,
    HumanDynamicsRequest,
)
from app.services.horizon_human_dynamics import HumanDynamicsEngine


def _base_request(**overrides):
    data = {
        "scenario": "A service announces a material price increase.",
        "scenario_id": "price-rise-baseline",
        "population": "active_customers",
        "horizon_hours": 168,
        "evidence_quality": 0.7,
        "options": [
            BehaviorOption(
                key="accept",
                label="Accept the change",
                base_rate=0.55,
                perceived_benefit=0.55,
                friction=0.25,
                norm_support=0.55,
                identity_alignment=0.55,
                habit_strength=0.8,
                network_exposure=0.45,
                urgency=0.35,
                threat_reduction=0.5,
                perceived_control=0.45,
                evidence_salience=0.65,
            ),
            BehaviorOption(
                key="leave",
                label="Leave the service",
                base_rate=0.25,
                perceived_benefit=0.65,
                friction=0.65,
                norm_support=0.45,
                identity_alignment=0.4,
                habit_strength=0.2,
                network_exposure=0.5,
                urgency=0.55,
                threat_reduction=0.7,
                perceived_control=0.65,
                evidence_salience=0.7,
            ),
        ],
    }
    data.update(overrides)
    return HumanDynamicsRequest(**data)


def _probability(result, key):
    return next(action["probability"] for action in result["actions"] if action["key"] == key)


def test_probabilities_sum_to_one_and_are_explicitly_uncalibrated():
    result = HumanDynamicsEngine().predict(_base_request())

    assert sum(action["probability"] for action in result["actions"]) == pytest.approx(1.0)
    assert result["prediction_status"] == "uncalibrated_model_estimate"
    assert result["empirically_calibrated"] is False
    assert result["probabilities_are_observed_frequencies"] is False
    assert result["critical_semantics"]["probability_is_model_estimate"] is True
    assert (
        result["critical_semantics"]["plausibility_band_is_statistical_confidence_interval"]
        is False
    )


def test_reliable_observation_moves_probability_in_expected_direction():
    engine = HumanDynamicsEngine()
    before = engine.predict(_base_request())
    after = engine.predict(
        _base_request(
            observations=[
                BehaviorObservation(
                    signal="Searches for cancellation instructions spike after the announcement.",
                    reliability=1.0,
                    likelihood_by_action={"leave": 4.0, "accept": 0.6},
                )
            ]
        )
    )

    assert _probability(after, "leave") > _probability(before, "leave")
    assert _probability(after, "accept") < _probability(before, "accept")
    assert after["evidence_updates"][0]["probability_shift"]["leave"] > 0


def test_social_mechanism_rewards_norm_and_network_exposure():
    request = HumanDynamicsRequest(
        scenario="A visible group norm forms around one of two equivalent actions.",
        population="online_community",
        horizon_hours=72,
        evidence_quality=0.6,
        mechanism_weights={
            "incentive": 0.0,
            "habit": 0.0,
            "social": 1.0,
            "stress": 0.0,
        },
        options=[
            BehaviorOption(
                key="follow_norm",
                label="Follow the visible norm",
                base_rate=0.5,
                norm_support=0.95,
                network_exposure=0.95,
                identity_alignment=0.7,
            ),
            BehaviorOption(
                key="ignore_norm",
                label="Ignore the visible norm",
                base_rate=0.5,
                norm_support=0.1,
                network_exposure=0.1,
                identity_alignment=0.4,
            ),
        ],
    )

    result = HumanDynamicsEngine().predict(request)

    assert result["leading_action"]["key"] == "follow_norm"
    assert _probability(result, "follow_norm") > 0.5


def test_counterfactual_compare_reports_probability_delta():
    baseline = _base_request()
    counterfactual = _base_request(
        scenario="The same price increase is paired with a strong loyalty benefit and easy cancellation.",
        scenario_id="price-rise-counterfactual",
        options=[
            baseline.options[0].model_copy(update={"perceived_benefit": 0.9}),
            baseline.options[1].model_copy(update={"friction": 0.2, "perceived_benefit": 0.8}),
        ],
    )

    result = HumanDynamicsEngine().compare(
        HumanDynamicsComparisonRequest(
            baseline=baseline,
            counterfactuals=[counterfactual],
        )
    )

    deltas = {
        row["key"]: row["delta"]
        for row in result["counterfactuals"][0]["action_deltas"]
    }
    assert any(abs(delta) > 0 for delta in deltas.values())
    assert result["critical_semantics"]["counterfactual_is_causal_effect_estimate"] is False


def test_observation_cannot_reference_unknown_action():
    with pytest.raises(ValidationError):
        _base_request(
            observations=[
                BehaviorObservation(
                    signal="A signal references a missing behavior.",
                    likelihood_by_action={"unknown_action": 2.0},
                )
            ]
        )
