from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonEmergingClusterRequest(BaseModel):
    bucket_minutes: int = Field(default=15, ge=5, le=60)
    lookback_buckets: int = Field(default=4, ge=1, le=24)
    min_articles: int = Field(default=3, ge=2, le=50)
