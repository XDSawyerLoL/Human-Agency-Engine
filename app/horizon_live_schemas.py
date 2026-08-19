from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


GDELT_QUERY_FAMILIES = {
    "supply",
    "weather_disaster",
    "conflict_security",
    "infrastructure",
    "economy_labor",
    "public_health",
}


class HorizonGdeltPollRequest(BaseModel):
    timespan_minutes: int = Field(default=15, ge=15, le=1440)
    max_records_per_query: int = Field(default=25, ge=1, le=50)
    families: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_families(self):
        unknown = sorted(set(self.families) - GDELT_QUERY_FAMILIES)
        if unknown:
            raise ValueError(f"unsupported GDELT query families: {', '.join(unknown)}")
        return self
