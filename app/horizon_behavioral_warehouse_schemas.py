from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WarehouseSource = Literal["openalex", "pubmed"]
MechanismName = Literal["incentive", "habit", "social", "stress", "intention_action", "collective_dynamics", "other"]
EffectDirection = Literal["positive", "negative", "null", "mixed", "unknown"]
StudyDesign = Literal[
    "meta_analysis",
    "systematic_review",
    "randomized_experiment",
    "quasi_experimental",
    "longitudinal",
    "observational",
    "cross_sectional",
    "qualitative",
    "simulation",
    "unknown",
]
ReplicationStatus = Literal["replicated", "mixed", "failed", "not_applicable", "unknown"]
EvidenceStatus = Literal["candidate", "accepted", "rejected"]


class BehavioralWarehouseHarvestRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    sources: list[WarehouseSource] = Field(default_factory=lambda: ["openalex", "pubmed"], min_length=1, max_length=2)
    limit_per_source: int = Field(default=10, ge=1, le=50)
    publication_year_from: int | None = Field(default=None, ge=1800, le=2200)
    publication_year_to: int | None = Field(default=None, ge=1800, le=2200)
    open_access_only: bool = False

    @model_validator(mode="after")
    def validate_years(self):
        if (
            self.publication_year_from is not None
            and self.publication_year_to is not None
            and self.publication_year_from > self.publication_year_to
        ):
            raise ValueError("publication_year_from cannot be after publication_year_to")
        return self


class BehavioralWarehouseBootstrapRequest(BaseModel):
    mechanisms: list[MechanismName] = Field(
        default_factory=lambda: ["incentive", "habit", "social", "stress", "intention_action", "collective_dynamics"],
        min_length=1,
        max_length=7,
    )
    scenario: str = Field(default="human behavior", min_length=3, max_length=500)
    population: str = Field(default="general population", min_length=1, max_length=240)
    max_queries: int = Field(default=8, ge=1, le=20)
    limit_per_source: int = Field(default=5, ge=1, le=20)
    publication_year_from: int | None = Field(default=2000, ge=1800, le=2200)
    open_access_only: bool = False


class BehavioralEffectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_key: str = Field(..., min_length=8, max_length=96)
    mechanism: MechanismName
    construct: str = Field(..., min_length=2, max_length=160)
    population: str = Field(..., min_length=1, max_length=1000)
    context: str = Field(..., min_length=1, max_length=1500)
    exposure: str = Field(..., min_length=1, max_length=1500)
    behavioral_outcome: str = Field(..., min_length=1, max_length=1500)
    effect_direction: EffectDirection
    effect_size: float | None = Field(default=None, ge=-1000000.0, le=1000000.0)
    effect_size_type: str | None = Field(default=None, max_length=64)
    uncertainty_low: float | None = Field(default=None, ge=-1000000.0, le=1000000.0)
    uncertainty_high: float | None = Field(default=None, ge=-1000000.0, le=1000000.0)
    sample_size: int | None = Field(default=None, ge=1, le=1000000000)
    study_design: StudyDesign = "unknown"
    replication_status: ReplicationStatus = "unknown"
    preregistered: bool | None = None
    peer_reviewed: bool | None = None
    countries: list[str] = Field(default_factory=list, max_length=64)
    time_horizon: str | None = Field(default=None, max_length=160)
    evidence_summary: str = Field(..., min_length=3, max_length=4000)
    source_locator: str | None = Field(default=None, max_length=512)
    extraction_method: Literal["human", "rule_based", "llm_assisted", "imported_dataset"] = "human"
    extraction_version: str | None = Field(default=None, max_length=96)
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_uncertainty(self):
        if self.uncertainty_low is not None and self.uncertainty_high is not None:
            if self.uncertainty_low > self.uncertainty_high:
                raise ValueError("uncertainty_low cannot exceed uncertainty_high")
        return self


class BehavioralEffectReview(BaseModel):
    status: EvidenceStatus
    reviewed_by: str = Field(..., min_length=1, max_length=160)
    notes: str = Field(default="", max_length=4000)


class BehavioralWarehouseCalibrationPackRequest(BaseModel):
    mechanisms: list[MechanismName] | None = Field(default=None, max_length=7)
    min_quality_score: float = Field(default=0.45, ge=0.0, le=1.0)
    min_effects_per_mechanism: int = Field(default=3, ge=1, le=1000)
    countries: list[str] = Field(default_factory=list, max_length=64)
    publication_year_from: int | None = Field(default=None, ge=1800, le=2200)
