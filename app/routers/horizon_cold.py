from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_cold_schemas import (
    HorizonColdRegionalAggregateRequest,
    HorizonMeteoFranceColdArchiveBackfillRequest,
    HorizonRteHeatingLoadBackfillRequest,
)
from ..security import require_api_key
from ..services.horizon_cold_backfill import HorizonColdHistoricalBackfillService
from ..services.horizon_cold_regions import HorizonRegionalColdService
from ..services.horizon_cold_response import HorizonColdResponseLibraryService
from ..services.horizon_rte_heating import HorizonRteHeatingLoadBackfillService

router = APIRouter(prefix="/horizon/cold", dependencies=[Depends(require_api_key)])


@router.post("/backfill/meteofrance")
def backfill_meteofrance_cold(
    payload: HorizonMeteoFranceColdArchiveBackfillRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonColdHistoricalBackfillService(db).backfill(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Météo-France grand-froid archive fetch failed: {exc}") from exc


@router.post("/regions/aggregate")
def aggregate_regional_cold(
    payload: HorizonColdRegionalAggregateRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonRegionalColdService(db).aggregate(
            start_at=payload.start_at,
            end_at=payload.end_at,
            merge_gap_hours=payload.merge_gap_hours,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/backfill/rte/heating-load")
def backfill_rte_heating_load(
    payload: HorizonRteHeatingLoadBackfillRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonRteHeatingLoadBackfillService(db).backfill(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"RTE eco2mix heating archive fetch failed: {exc}") from exc


@router.post("/response-pattern/sync")
def sync_cold_response_pattern(db: Session = Depends(get_db)):
    row = HorizonColdResponseLibraryService(db).sync()
    return {
        "pattern_id": row.id,
        "pattern_key": row.pattern_key,
        "event_types": row.event_types,
        "materialization_signal_types": (row.provenance or {}).get("materialization_signal_types", []),
        "formal_probability": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
