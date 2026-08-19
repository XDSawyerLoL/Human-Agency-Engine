from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonFuelNormalizeRequest(BaseModel):
    min_reporting_stations: int = Field(default=5, ge=2, le=1000)
    min_temporary_ruptures: int = Field(default=3, ge=1, le=1000)
    min_rupture_rate: float = Field(default=0.10, ge=0.01, le=1.0)
