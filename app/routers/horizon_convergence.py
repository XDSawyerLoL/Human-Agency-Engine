from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_convergence_schemas import (
    HorizonConvergenceSnapshotRequest,
    HorizonLiveConvergencePollRequest,
    HorizonRteRealtimePollRequest,
    HorizonSncfPollRequest,
    HorizonVigicruesPollRequest,
)
from ..security import require_api_key
from ..services.horizon_convergence import HorizonConvergenceService
from ..services.horizon_live_convergence import HorizonLiveConvergenceService
from ..services.horizon_rte_realtime import HorizonRteRealtimeService
from ..services.horizon_sncf import HorizonSncfService
from ..services.horizon_vigicrues import HorizonVigicruesService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.get("/convergence/capabilities")
def convergence_capabilities():
    return HorizonConvergenceService.capability_matrix()


@router.post("/convergence/events/{event_id}/snapshot")
def build_convergence_snapshot(
    event_id: int,
    payload: HorizonConvergenceSnapshotRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonConvergenceService(db).build_snapshot(event_id, as_of=payload.as_of)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/convergence/events/{event_id}/snapshots")
def list_convergence_snapshots(
    event_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return HorizonConvergenceService(db).list_snapshots(event_id, limit=limit)


@router.post("/live/rte-realtime/poll")
def poll_rte_realtime(
    payload: HorizonRteRealtimePollRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonRteRealtimeService(db).poll(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/live/vigicrues/poll")
def poll_vigicrues(
    payload: HorizonVigicruesPollRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonVigicruesService(db).poll(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/live/sncf/poll")
def poll_sncf(
    payload: HorizonSncfPollRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonSncfService(db).poll(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/live/convergence/poll")
def poll_live_convergence(
    payload: HorizonLiveConvergencePollRequest,
    db: Session = Depends(get_db),
):
    return HorizonLiveConvergenceService(db).poll(payload)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
