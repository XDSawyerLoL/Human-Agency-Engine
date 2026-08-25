from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


MechanismName = Literal["incentive", "habit", "social", "stress"]


class BehaviorOption(BaseModel):
    key: str = Field(..., min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    label: str = Field(..., min_length=1, max_length=180)
    base_rate: float = Field(
        default=0.5,
        gt=0.0,
        lt=1.0,
        description="Prior propensity for this action within the requested horizon.",
    )
    perceived_benefit: float = Field(default=0.5, ge=0.0, le=1.0)
    friction: float = Field(default=0.5, ge=0.0, le=1.0)
    norm_support: float = Field(default=0.5, ge=0.0, le=1.0)
    identity_alignment: float = Field(default=0.5, ge=0.0, le=1.0)
    habit_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    network_exposure: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    threat_reduction: float = Field(default=0.5, ge=0.0, le=1.0)
    perceived_control: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_salience: float = Field(default=0.5, ge=0.0, le=1.0)
    typical_latency_hours: float | None = Field(default=None, gt=0.0, le=8760.0)


class BehaviorObservation(BaseModel):
    signal: str = Field(..., min_length=1, max_length=240)
    likelihood_by_action: dict[str, float] = Field(
        default_factory=dict,
        description="Likelihood ratios by action. Values above 1 support an action; below 1 weaken it.",
    )
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_likelihood_ratios(self):
        for action_key, ratio in self.likelihood_by_action.items():
            if not 0.05 <= ratio <= 20.0:
                raise ValueError(
                    f"likelihood ratio for {action_key!r} must be between 0.05 and 20"
                )
        return self


class HumanDynamicsRequest(BaseModel):
    scenario: str = Field(..., min_length=3, max_length=1000)
    scenario_id: str | None = Field(default=None, max_length=120)
    population: str = Field(default="general_population", min_length=1, max_length=240)
    horizon_hours: float = Field(default=168.0, gt=0.0, le=8760.0)
    evidence_quality: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Quality/completeness of evidence supporting the feature values.",
    )
    options: list[BehaviorOption] = Field(..., min_length=2, max_length=12)
    observations: list[BehaviorObservation] = Field(default_factory=list, max_length=40)
    mechanism_weights: dict[MechanismName, float] | None = None

    @model_validator(mode="after")
    def validate_action_keys(self):
        keys = [option.key for option in self.options]
        if len(keys) != len(set(keys)):
            raise ValueError("behavior option keys must be unique")
        key_set = set(keys)
        for observation in self.observations:
            unknown = set(observation.likelihood_by_action) - key_set
            if unknown:
                raise ValueError(
                    "observation references unknown action keys: "
                    + ", ".join(sorted(unknown))
                )
        if self.mechanism_weights is not None:
            if not self.mechanism_weights:
                raise ValueError("mechanism_weights cannot be empty")
            if any(value < 0.0 for value in self.mechanism_weights.values()):
                raise ValueError("mechanism_weights cannot contain negative values")
            if sum(self.mechanism_weights.values()) <= 0.0:
                raise ValueError("mechanism_weights must contain a positive value")
        return self


class HumanDynamicsComparisonRequest(BaseModel):
    baseline: HumanDynamicsRequest
    counterfactuals: list[HumanDynamicsRequest] = Field(..., min_length=1, max_length=8)
