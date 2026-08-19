from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonImpactRequest(BaseModel):
    event_id: int
    pattern_id: int
    as_of: datetime | None = None
    mode: str = Field(default="live", pattern="^(live|backtest)$")

    @model_validator(mode="after")
    def validate_cutoff(self):
        if self.mode == "backtest" and self.as_of is None:
            raise ValueError("backtest mode requires as_of")
        return self
