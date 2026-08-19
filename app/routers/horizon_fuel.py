from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_fuel_schemas import HorizonFuelNormalizeRequest
from ..security import require_api_key
from ..services.horizon_fuel import HorizonFuelService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.post("/live/fuel-ruptures/poll")
def poll_fuel_ruptures(db: Session = Depends(get_db)):
    try:
        return HorizonFuelService(db).poll()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/normalize/fuel-ruptures/latest")
def normalize_latest_fuel_ruptures(
    payload: HorizonFuelNormalizeRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonFuelService(db).normalize_latest(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
