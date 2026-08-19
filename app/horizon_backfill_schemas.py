from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonMeteoFranceArchiveBackfillRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    departments: list[str] = Field(default_factory=list, max_length=120)
    min_color_id: int = Field(default=3, ge=2, le=4)
    max_snapshots: int = Field(default=500, ge=1, le=5000)
    merge_gap_hours: int = Field(default=24, ge=0, le=72)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class HorizonRteCoolingLoadBackfillRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    baseline_lookback_days: int = Field(default=28, ge=14, le=84)
    minimum_lift_ratio: float = Field(default=0.03, ge=0.005, le=0.25)
    minimum_afternoon_points: int = Field(default=12, ge=8, le=20)
    max_records: int = Field(default=50000, ge=100, le=100000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self
