from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


SOURCE_CLASSES = {
    "official_primary",
    "official_statistical",
    "news_global",
    "behavioral_signal",
    "social_weak_signal",
}


class HorizonSourceUpsert(BaseModel):
    source_key: str = Field(min_length=3, max_length=128)
    name: str = Field(min_length=3, max_length=255)
    source_class: str
    adapter_kind: str = Field(min_length=2, max_length=64)
    domains: list[str] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    base_locator: str = ""
    trust_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    refresh_seconds: int = Field(default=900, ge=60, le=86400)
    requires_credentials: bool = False
    enabled: bool = True
    metadata_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_class(self):
        if self.source_class not in SOURCE_CLASSES:
            raise ValueError("unsupported HORIZON source_class")
        return self


class HorizonObservationIngest(BaseModel):
    external_key: str = Field(min_length=3, max_length=192)
    observation_type: str = Field(min_length=2, max_length=64)
    title: str = Field(default="", max_length=255)
    summary: str = ""
    source_url: str = ""
    geography: list[str] = Field(default_factory=list)
    canonical_facts: dict = Field(default_factory=dict)
    raw_metadata: dict = Field(default_factory=dict)
    event_time: datetime | None = None
    published_at: datetime | None = None
    observed_at: datetime


class HorizonCandidateBuild(BaseModel):
    observation_ids: list[int] = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=2, max_length=96)
    title: str = Field(min_length=3, max_length=255)
    geography: list[str] = Field(default_factory=list)
    normalized_facts: dict = Field(default_factory=dict)
    normalizer_version: str = Field(default="", max_length=96)
