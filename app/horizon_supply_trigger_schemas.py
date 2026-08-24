from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonGdeltFuelSupplyTriggerBackfillRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    min_distinct_domains_per_day: int = Field(default=2, ge=1, le=20)
    max_days: int = Field(default=31, ge=1, le=31)
    max_events_per_day: int = Field(default=500, ge=10, le=5000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        span_days = (self.end_at.date() - self.start_at.date()).days + 1
        if span_days > self.max_days:
            raise ValueError(
                f"requested GDELT trigger window spans {span_days} days; max_days={self.max_days}"
            )
        if self.start_at.date() < datetime(2013, 4, 1).date():
            raise ValueError(
                "GDELT 1.0 SOURCEURL-based fuel relevance requires April 1, 2013 or later"
            )
        return self
