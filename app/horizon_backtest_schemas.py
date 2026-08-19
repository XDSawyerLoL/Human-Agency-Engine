from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonHistoricalBacktestRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    evaluation_as_of: datetime
    event_types: list[str] = Field(default_factory=list, max_length=50)
    max_events: int = Field(default=250, ge=1, le=1000)
    max_cases: int = Field(default=2000, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.evaluation_as_of < self.end_at:
            raise ValueError("evaluation_as_of must be at or after end_at")
        return self
