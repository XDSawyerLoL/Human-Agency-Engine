from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_collector_schemas import HorizonCollectorRunRequest
from ..security import require_api_key
from ..services.horizon_collector import HorizonCollectorService

router = APIRouter(prefix="/horizon/collector", dependencies=[Depends(require_api_key)])


@router.get("/status")
def collector_status(
    cycle_limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return HorizonCollectorService(db).status(cycle_limit=cycle_limit)


@router.post("/run-due")
def run_due_collector_cycle(
    payload: HorizonCollectorRunRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonCollectorService(db).run_due(
            owner_id=payload.owner_id,
            force_sources=payload.force_sources,
            trigger="api",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
