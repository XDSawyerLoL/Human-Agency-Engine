from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_cascade_schemas import HorizonCascadeRequest
from ..security import require_api_key
from ..services.horizon_cascade import HorizonCascadeService

router = APIRouter(prefix="/horizon/cascades", dependencies=[Depends(require_api_key)])


@router.post("/project")
def project_collective_behavior_cascade(
    payload: HorizonCascadeRequest,
    db: Session = Depends(get_db),
):
    try:
        row = HorizonCascadeService(db).project(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "id": row.id,
        "cascade_key": row.cascade_key,
        "engine": HorizonCascadeService.ENGINE_VERSION,
        "event_id": row.event_id,
        "pattern_id": row.pattern_id,
        "mode": row.mode,
        "as_of": row.as_of,
        "stages": row.stage_snapshot,
        "current_stage_index": row.current_stage_index,
        "current_stage": row.current_stage,
        "next_stage": row.next_stage or None,
        "propagation_score": row.propagation_score,
        "acceleration_score": row.acceleration_score,
        "evidence_diversity_score": row.evidence_diversity_score,
        "confidence_band": row.confidence_band,
        "probability_basis": row.probability_basis,
        "interpretation": row.interpretation,
        "evidence": row.evidence_snapshot,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
