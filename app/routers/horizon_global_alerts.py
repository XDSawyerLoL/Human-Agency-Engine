from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_global_alert_schemas import (
    HorizonGdacsPollRequest,
    HorizonGlobalAlertNormalizeRequest,
    HorizonMeteoAlarmPollRequest,
)
from ..security import require_api_key
from ..services.horizon_gdacs import HorizonGdacsService
from ..services.horizon_global_alert_normalizer import HorizonGlobalAlertNormalizer
from ..services.horizon_meteoalarm import HorizonMeteoAlarmService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.post("/live/gdacs/poll")
def poll_gdacs(payload: HorizonGdacsPollRequest, db: Session = Depends(get_db)):
    try:
        return HorizonGdacsService(db).poll(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/gdacs/normalize/latest")
def normalize_latest_gdacs(
    payload: HorizonGlobalAlertNormalizeRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonGlobalAlertNormalizer(db).normalize_latest_gdacs(
            max_observations=payload.max_observations
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/live/meteoalarm/poll")
def poll_meteoalarm(payload: HorizonMeteoAlarmPollRequest, db: Session = Depends(get_db)):
    try:
        return HorizonMeteoAlarmService(db).poll(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/meteoalarm/normalize/latest")
def normalize_latest_meteoalarm(
    payload: HorizonGlobalAlertNormalizeRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonGlobalAlertNormalizer(db).normalize_latest_meteoalarm(
            max_observations=payload.max_observations
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
