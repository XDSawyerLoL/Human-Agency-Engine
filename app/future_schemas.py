from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Direction = Literal["higher_is_better", "lower_is_better"]
EvidenceLevel = Literal[
    "none",
    "observational",
    "personal_repeated",
    "quasi_experimental",
    "experimental",
]


class MetricEffect(BaseModel):
    low: float
    central: float
    high: float
    unit: str = ""
    direction: Direction = "higher_is_better"
    rationale: str = ""

    @model_validator(mode="after")
    def validate_bounds(self):
        if not self.low <= self.central <= self.high:
            raise ValueError("metric effect must satisfy low <= central <= high")
        return self


class ScenarioAssumption(BaseModel):
    statement: str
    confidence: float = Field(..., ge=0, le=1)
    source: str = "user"
    falsifiable_by: str = ""


class ScenarioEvidence(BaseModel):
    level: EvidenceLevel = "none"
    sources: list[str] = Field(default_factory=list)
    notes: str = ""


class FutureScenarioInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    intervention: dict = Field(default_factory=dict)
    effects: dict[str, MetricEffect] = Field(default_factory=dict)
    assumptions: list[ScenarioAssumption] = Field(default_factory=list)
    evidence: ScenarioEvidence = Field(default_factory=ScenarioEvidence)


class FutureCompareRequest(BaseModel):
    horizon_days: int = Field(90, ge=1, le=3650)
    objective: str = Field("", max_length=2000)
    scenarios: list[FutureScenarioInput] = Field(..., min_length=1, max_length=10)


class ForecastOutcomeCreate(BaseModel):
    scenario_id: int | None = None
    observed_metrics: dict = Field(default_factory=dict)
    observation_window: dict = Field(default_factory=dict)
    notes: str = Field("", max_length=4000)


class FutureScenarioOut(BaseModel):
    id: int
    run_id: int
    name: str
    scenario_type: str
    intervention: dict
    assumptions: list
    projected_metrics: dict
    uncertainty: dict
    evidence: dict
    agency_delta: dict
    confidence: float
    claim_level: str
    robustness: str
    created_at: datetime

    model_config = {"from_attributes": True}
