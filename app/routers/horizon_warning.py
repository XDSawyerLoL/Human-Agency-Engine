from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_warning_schemas import HorizonWarningProjectRequest, HorizonWarningRefreshRequest
from ..security import require_api_key
from ..services.horizon_warning import HorizonWarningService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.post("/warnings/project")
def project_warning(payload: HorizonWarningProjectRequest, db: Session = Depends(get_db)):
    try:
        row = HorizonWarningService(db).project(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "snapshot_id": row.id,
        "episode_id": row.episode_id,
        "as_of": row.as_of,
        "signal_families": row.signal_families,
        "family_count": row.family_count,
        "source_count": row.source_count,
        "convergence_score": row.convergence_score,
        "convergence_band": row.convergence_band,
        "cascade_stage": row.cascade_stage,
        "expected_onset_low": row.expected_onset_low,
        "expected_onset_high": row.expected_onset_high,
        "remaining_lead_low_hours": row.remaining_lead_low_hours,
        "remaining_lead_high_hours": row.remaining_lead_high_hours,
        "evidence": row.evidence_snapshot,
        "interpretation": row.interpretation,
    }


@router.post("/warnings/refresh")
def refresh_warnings(payload: HorizonWarningRefreshRequest, db: Session = Depends(get_db)):
    return HorizonWarningService(db).refresh(payload)


from .agency import router as agency_router
agency_router.include_router(router)
