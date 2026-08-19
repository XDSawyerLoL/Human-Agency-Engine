from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonReevaluationRequest(BaseModel):
    max_events: int = Field(default=100, ge=1, le=1000)
    max_users: int = Field(default=5000, ge=1, le=50000)
    material_score_delta: float = Field(default=0.12, ge=0.01, le=0.5)
