from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonEventCreate(BaseModel):
    event_key: str = Field(min_length=3, max_length=160)
    event_type: str = Field(min_length=2, max_length=96)
    title: str = Field(min_length=3, max_length=255)
    summary: str = ""
    geography: list[str] = Field(default_factory=list)
    source: str = Field(min_length=2, max_length=96)
    source_url: str = ""
    source_reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_facts: dict = Field(default_factory=dict)
    occurred_at: datetime
    first_observed_at: datetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.first_observed_at < self.occurred_at:
            raise ValueError("first_observed_at cannot be before occurred_at")
        return self


class HorizonSignalCreate(BaseModel):
    signal_key: str = Field(min_length=3, max_length=192)
    signal_type: str = Field(min_length=2, max_length=96)
    source: str = Field(min_length=2, max_length=96)
    geography: list[str] = Field(default_factory=list)
    value: float | None = None
    baseline: float | None = None
    normalized_score: float = Field(default=0.0, ge=-10.0, le=10.0)
    direction: str = Field(default="unknown", pattern="^(up|down|flat|mixed|unknown)$")
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: dict = Field(default_factory=dict)
    observed_at: datetime


class HorizonPatternCreate(BaseModel):
    pattern_key: str = Field(min_length=3, max_length=160)
    name: str = Field(min_length=3, max_length=255)
    event_types: list[str] = Field(default_factory=list)
    required_signal_types: list[str] = Field(default_factory=list)
    predicted_response: str = Field(min_length=3)
    mechanism_chain: list[str] = Field(default_factory=list)
    expected_lag_hours_low: int = Field(default=0, ge=0, le=8760)
    expected_lag_hours_high: int = Field(default=168, ge=1, le=8760)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    support_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    provenance: dict = Field(default_factory=dict)
    knowledge_available_at: datetime

    @model_validator(mode="after")
    def validate_lag(self):
        if self.expected_lag_hours_high < self.expected_lag_hours_low:
            raise ValueError("expected_lag_hours_high must be >= expected_lag_hours_low")
        return self


class HorizonForecastRequest(BaseModel):
    event_id: int
    as_of: datetime | None = None
    mode: str = Field(default="live", pattern="^(live|backtest)$")

    @model_validator(mode="after")
    def validate_backtest_cutoff(self):
        if self.mode == "backtest" and self.as_of is None:
            raise ValueError("backtest mode requires as_of")
        return self


class HorizonResolutionCreate(BaseModel):
    outcome_occurred: bool | None = None
    outcome_summary: str = ""
    correctness: str = Field(default="inconclusive", pattern="^(confirmed|partial|false|inconclusive)$")
    became_obvious_at: datetime | None = None
    personal_action_at: datetime | None = None
    notes: str = ""
