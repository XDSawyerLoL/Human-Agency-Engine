from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonWarningProjectRequest(BaseModel):
    event_id: int
    pattern_id: int
    as_of: datetime | None = None
    mode: str = Field(default="live", pattern="^(live|backtest)$")
    recency_hours: int = Field(default=72, ge=1, le=24 * 30)

    @model_validator(mode="after")
    def validate_cutoff(self):
        if self.mode == "backtest" and self.as_of is None:
            raise ValueError("backtest mode requires as_of")
        return self


class HorizonWarningRefreshRequest(BaseModel):
    max_events: int = Field(default=100, ge=1, le=1000)
    recency_hours: int = Field(default=72, ge=1, le=24 * 30)
