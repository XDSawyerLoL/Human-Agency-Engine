from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_materialization_schemas import HorizonMaterializationScanRequest
from ..security import require_api_key
from ..services.horizon_materialization import HorizonMaterializationService

router = APIRouter(prefix="/horizon/materialization", dependencies=[Depends(require_api_key)])


@router.post("/scan")
def scan_materialization(
    payload: HorizonMaterializationScanRequest,
    db: Session = Depends(get_db),
):
    return HorizonMaterializationService(db).scan(payload)


@router.get("/detections")
def list_materialization_detections(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = HorizonMaterializationService(db).list_detections(limit=limit)
    return [
        {
            "id": row.id,
            "forecast_id": row.forecast_id,
            "event_id": row.event_id,
            "pattern_id": row.pattern_id,
            "became_obvious_at": row.became_obvious_at,
            "predictive_lead_time_hours": row.predictive_lead_time_hours,
            "evidence_signal_ids": row.evidence_signal_ids,
            "evidence_sources": row.evidence_sources,
            "materialization_signal_types": row.materialization_signal_types,
            "rule": row.rule_snapshot,
            "created_at": row.created_at,
        }
        for row in rows
    ]


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
