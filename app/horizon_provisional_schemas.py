from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonProvisionalRefreshRequest(BaseModel):
    max_candidates: int = Field(default=100, ge=1, le=1000)


class HorizonProvisionalReconcileRequest(BaseModel):
    max_forecasts: int = Field(default=500, ge=1, le=5000)
