from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.horizon_briefing import HorizonWorldBriefingService
from ..services.human_signal_engine import HumanSignalEngine


router = APIRouter()


@router.get("/human-signals/opportunities")
def human_signal_opportunities(
    external_id: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=20, ge=1, le=100),
    event_limit: int = Query(default=120, ge=1, le=200),
    candidate_limit: int = Query(default=120, ge=1, le=200),
    db: Session = Depends(get_db),
):
    briefing = HorizonWorldBriefingService(db).snapshot(
        external_id=external_id,
        event_limit=event_limit,
        candidate_limit=candidate_limit,
        forecast_limit=1,
    )
    return HumanSignalEngine().analyze(briefing, limit=limit)
