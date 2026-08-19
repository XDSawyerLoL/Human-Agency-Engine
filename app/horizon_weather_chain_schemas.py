from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonWeatherChainReconcileRequest(BaseModel):
    max_forecasts: int = Field(default=1000, ge=1, le=5000)
    max_chains: int = Field(default=1000, ge=1, le=5000)
