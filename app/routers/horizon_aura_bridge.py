from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..services.horizon_aura_bridge import HorizonAuraBridgeService


router = APIRouter(
    prefix="/horizon/aura",
    dependencies=[Depends(require_api_key)],
)


@router.get("/feed")
def aura_feed(
    external_id: str | None = Query(default=None, max_length=160),
    event_limit: int = Query(default=100, ge=1, le=200),
    candidate_limit: int = Query(default=100, ge=1, le=200),
    forecast_limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return HorizonAuraBridgeService(db).snapshot(
        external_id=external_id,
        event_limit=event_limit,
        candidate_limit=candidate_limit,
        forecast_limit=forecast_limit,
    )


@router.get("/capabilities")
def aura_capabilities():
    return HorizonAuraBridgeService.capabilities()
