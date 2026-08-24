from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class HorizonFuelNormalizeRequest(BaseModel):
    min_reporting_stations: int = Field(default=5, ge=2, le=1000)
    min_temporary_ruptures: int = Field(default=3, ge=1, le=1000)
    min_rupture_rate: float = Field(default=0.10, ge=0.01, le=1.0)



class HorizonFuelHistoricalBackfillRequest(BaseModel):
    year: int = Field(ge=2007, le=2100)
    departments: list[str] = Field(default_factory=list, max_length=120)
    min_reporting_stations: int = Field(default=5, ge=2, le=5000)
    min_temporary_ruptures: int = Field(default=3, ge=1, le=5000)
    min_rupture_rate: float = Field(default=0.10, ge=0.01, le=1.0)
    max_observations: int = Field(default=20000, ge=100, le=100000)

    @field_validator("departments")
    @classmethod
    def normalize_departments(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip().upper() for item in value if str(item).strip()})
