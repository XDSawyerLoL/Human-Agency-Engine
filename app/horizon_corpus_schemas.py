from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


HORIZON_CORPUS_STRATEGIES = ("heat-mf-rte-v1", "cold-mf-rte-v1")


class HorizonCalibrationCorpusBuildRequest(BaseModel):
    strategy: Literal["heat-mf-rte-v1", "cold-mf-rte-v1"] = "heat-mf-rte-v1"
    start_at: datetime
    end_at: datetime
    slice_days: int = Field(default=30, ge=7, le=60)
    outcome_grace_days: int = Field(default=7, ge=4, le=14)
    max_slices_per_call: int = Field(default=2, ge=1, le=12)

    departments: list[str] = Field(default_factory=list, max_length=120)
    meteo_min_color_id: int = Field(default=3, ge=2, le=4)
    meteo_max_snapshots_per_slice: int = Field(default=500, ge=50, le=5000)
    meteo_merge_gap_hours: int = Field(default=24, ge=0, le=72)

    rte_baseline_lookback_days: int = Field(default=28, ge=14, le=84)
    rte_minimum_lift_ratio: float = Field(default=0.03, ge=0.005, le=0.25)
    rte_minimum_afternoon_points: int = Field(default=12, ge=8, le=20)
    rte_minimum_daily_points: int = Field(default=40, ge=24, le=50)
    rte_max_records_per_slice: int = Field(default=50000, ge=1000, le=100000)

    backtest_max_events: int = Field(default=500, ge=1, le=1000)
    backtest_max_cases: int = Field(default=3000, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if (self.end_at - self.start_at).days > 3660:
            raise ValueError("one calibration corpus request is limited to 10 years")
        self.departments = sorted({str(item).strip().upper() for item in self.departments if str(item).strip()})
        return self
