from __future__ import annotations

from fastapi import APIRouter

from ..horizon_human_dynamics_schemas import (
    HumanDynamicsComparisonRequest,
    HumanDynamicsRequest,
)
from ..services.horizon_human_dynamics import HumanDynamicsEngine


router = APIRouter(tags=["HORIZON Human Dynamics"])


@router.post("/horizon/human-dynamics/predict")
def predict_human_dynamics(payload: HumanDynamicsRequest):
    return HumanDynamicsEngine().predict(payload)


@router.post("/horizon/human-dynamics/compare")
def compare_human_dynamics(payload: HumanDynamicsComparisonRequest):
    return HumanDynamicsEngine().compare(payload)


@router.get("/horizon/human-dynamics/spec")
def human_dynamics_spec():
    return {
        "engine": HumanDynamicsEngine.ENGINE_VERSION,
        "purpose": (
            "Estimate competing human actions from multiple behavioral mechanisms, "
            "update them with explicit likelihood evidence, and compare counterfactual scenarios."
        ),
        "mechanisms": ["incentive", "habit", "social", "stress"],
        "empirically_calibrated": False,
        "probability_semantics": "model_estimate_not_observed_frequency",
        "intended_use": [
            "scenario analysis",
            "population-level behavioral forecasting",
            "early-warning hypothesis ranking",
            "counterfactual sensitivity analysis",
        ],
        "not_intended_as": [
            "certainty about an individual",
            "causal proof",
            "high-stakes automated decisioning",
        ],
    }
