from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_expiry_schemas import HorizonForecastExpiryScanRequest
from ..security import require_api_key
from ..services.horizon_expiry import HorizonForecastExpiryService

router = APIRouter(prefix="/horizon/expiry", dependencies=[Depends(require_api_key)])


@router.post("/scan")
def scan_expired_forecasts(
    payload: HorizonForecastExpiryScanRequest,
    db: Session = Depends(get_db),
):
    return HorizonForecastExpiryService(db).scan(payload)


@router.get("/detections")
def list_expiries(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    rows = HorizonForecastExpiryService(db).list_expiries(limit)
    return [
        {
            "id": row.id,
            "forecast_id": row.forecast_id,
            "event_id": row.event_id,
            "pattern_id": row.pattern_id,
            "expected_onset_high": row.expected_onset_high,
            "grace_hours": row.grace_hours,
            "expiry_deadline": row.expiry_deadline,
            "expired_at": row.expired_at,
            "checked_materialization_signal_types": row.checked_materialization_signal_types,
            "rule": row.rule_snapshot,
        }
        for row in rows
    ]


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
