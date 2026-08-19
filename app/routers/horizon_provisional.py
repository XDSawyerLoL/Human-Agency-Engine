from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_provisional_schemas import HorizonProvisionalReconcileRequest, HorizonProvisionalRefreshRequest
from ..security import require_api_key
from ..services.horizon_provisional import HorizonProvisionalService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.post("/provisional-forecasts/refresh")
def refresh_provisional_forecasts(
    payload: HorizonProvisionalRefreshRequest,
    db: Session = Depends(get_db),
):
    return HorizonProvisionalService(db).refresh(payload)


@router.post("/provisional-forecasts/reconcile")
def reconcile_provisional_forecasts(
    payload: HorizonProvisionalReconcileRequest,
    db: Session = Depends(get_db),
):
    return HorizonProvisionalService(db).reconcile(payload)


from .agency import router as agency_router
agency_router.include_router(router)
