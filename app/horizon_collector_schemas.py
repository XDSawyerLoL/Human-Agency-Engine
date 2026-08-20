from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


COLLECTOR_SOURCE_KEYS = {
    "gdelt",
    "gdacs",
    "meteofrance",
    "meteoalarm",
    "fuel",
    "rte_realtime",
    "vigicrues",
    "sncf",
    "windy",
    "synthesis",
}


class HorizonCollectorRunRequest(BaseModel):
    owner_id: str = Field(default="api-manual", min_length=1, max_length=255)
    force_sources: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_sources(self):
        normalized = list(dict.fromkeys(str(item).strip().lower() for item in self.force_sources if str(item).strip()))
        unsupported = sorted(set(normalized) - COLLECTOR_SOURCE_KEYS)
        if unsupported:
            raise ValueError(f"unsupported collector source(s): {', '.join(unsupported)}")
        self.force_sources = normalized
        return self
