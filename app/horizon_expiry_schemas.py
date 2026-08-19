from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HorizonForecastExpiryScanRequest(BaseModel):
    mode: Literal["live", "backtest", "all"] = "live"
    as_of: datetime | None = None
    max_forecasts: int = Field(default=500, ge=1, le=5000)
    forecast_ids: list[int] = Field(default_factory=list, max_length=500)
