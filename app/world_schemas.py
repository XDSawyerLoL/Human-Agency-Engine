from datetime import datetime

from pydantic import BaseModel, Field


class HypothesisCreate(BaseModel):
    name: str
    cause_pattern: dict = Field(default_factory=dict)
    effect_pattern: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    direction: str = Field("unknown", pattern="^(positive|negative|mixed|unknown)$")
    provenance: dict = Field(default_factory=dict)


class EventCreate(BaseModel):
    event_type: str
    source: str = "user"
    subject_type: str = ""
    subject_id: str = ""
    payload: dict = Field(default_factory=dict)
    confidence: float = Field(1.0, ge=0, le=1)
    occurred_at: datetime | None = None
    causation_id: str = ""
    correlation_id: str = ""


class ExperimentCreate(BaseModel):
    title: str
    scenario_id: int | None = None
    hypothesis_id: int | None = None
    intervention: dict = Field(default_factory=dict)
    expected_effects: dict = Field(default_factory=dict)
    stop_conditions: list = Field(default_factory=list)
    rollback_plan: dict = Field(default_factory=dict)
    reversible: bool = True


class ExperimentAuthorize(BaseModel):
    confirm: str
    irreversible_ack: bool = False


class ExperimentObservationCreate(BaseModel):
    metrics: dict = Field(default_factory=dict)
    verdict: str = Field("inconclusive", pattern="^(supports|contradicts|inconclusive)$")
    quality: float = Field(0.5, ge=0, le=1)
    notes: str = ""


class EvidenceCreate(BaseModel):
    event_id: int | None = None
    experiment_id: int | None = None
    observation_id: int | None = None
    verdict: str = Field(..., pattern="^(supports|contradicts|inconclusive)$")
    quality: float = Field(0.5, ge=0, le=1)
    notes: str = ""
