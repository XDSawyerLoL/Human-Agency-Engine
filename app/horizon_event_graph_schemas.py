from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class HorizonEventGraphBuildRequest(BaseModel):
    as_of: datetime | None = None
    lookback_hours: int = Field(default=336, ge=24, le=24 * 90)
    max_events: int = Field(default=500, ge=1, le=1500)
    max_candidates: int = Field(default=500, ge=1, le=1500)
    max_signals: int = Field(default=2000, ge=1, le=10000)
    minimum_same_episode_score: float = Field(default=0.72, ge=0.50, le=1.0)
    minimum_dependency_score: float = Field(default=0.68, ge=0.50, le=1.0)

    @model_validator(mode="after")
    def validate_graph_bounds(self):
        if self.minimum_same_episode_score < 0.60:
            raise ValueError("same-episode threshold is too permissive for HORIZON")
        if self.max_events + self.max_candidates > 2000:
            raise ValueError("event graph pairwise node budget cannot exceed 2000 event/candidate nodes")
        return self
