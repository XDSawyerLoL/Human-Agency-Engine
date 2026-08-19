from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_backfill_schemas import HorizonMeteoFranceArchiveBackfillRequest
from ..security import require_api_key
from ..services.horizon_backfill import HorizonHistoricalBackfillService
from ..services.horizon_coverage import HorizonHistoricalCoverageService

router = APIRouter(prefix="/horizon/backfill", dependencies=[Depends(require_api_key)])


@router.post("/meteofrance/vigilance")
def backfill_meteofrance_vigilance(
    payload: HorizonMeteoFranceArchiveBackfillRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonHistoricalBackfillService(db).backfill_meteofrance_vigilance(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Météo-France archive fetch failed: {exc}") from exc


@router.get("/runs")
def list_backfill_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return HorizonHistoricalBackfillService(db).list_runs(limit=limit)


@router.get("/coverage")
def list_historical_coverage(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return HorizonHistoricalCoverageService(db).list_intervals(limit=limit)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
