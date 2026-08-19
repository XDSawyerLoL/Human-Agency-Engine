from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from ..security import require_api_key
from ..services.horizon_event_graph import HorizonEventGraphService

router = APIRouter(prefix="/horizon/event-graph", dependencies=[Depends(require_api_key)])


@router.post("/build")
def build_event_graph(
    payload: HorizonEventGraphBuildRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonEventGraphService(db).build(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/snapshots")
def list_event_graph_snapshots(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return HorizonEventGraphService(db).list_snapshots(limit=limit)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
