from __future__ import annotations

from pydantic import BaseModel, Field


class HorizonMediaAttentionRefreshRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=6, le=72)
    recent_intervals: int = Field(default=4, ge=2, le=12)
    min_recent_articles: int = Field(default=5, ge=1, le=500)
    min_ratio: float = Field(default=1.5, ge=1.05, le=10.0)
    max_events: int = Field(default=20, ge=1, le=100)
    event_ids: list[int] = Field(default_factory=list, max_length=100)
