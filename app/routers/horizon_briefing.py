from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..services.horizon_briefing import HorizonWorldBriefingService


router = APIRouter(prefix="/horizon/world", dependencies=[Depends(require_api_key)])


@router.get("/briefing")
def world_briefing(
    external_id: str | None = Query(default=None, max_length=160),
    event_limit: int = Query(default=60, ge=1, le=200),
    candidate_limit: int = Query(default=60, ge=1, le=200),
    forecast_limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return HorizonWorldBriefingService(db).snapshot(
        external_id=external_id,
        event_limit=event_limit,
        candidate_limit=candidate_limit,
        forecast_limit=forecast_limit,
    )


from .horizon_human_signals import router as human_signal_router  # noqa: E402

router.include_router(human_signal_router)

from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
