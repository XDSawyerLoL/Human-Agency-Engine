from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.acquisition import InformationAcquisitionService
from ..services.synthesis import SynthesisService
from ..synthesis_models import CandidateIntervention
from .acquisition import router as acquisition_router

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
router.include_router(acquisition_router)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


@router.post("/users/{external_id}/synthesis/run")
def run_synthesis(
    external_id: str,
    horizon_days: int = Query(default=90, ge=1, le=3650),
    limit: int = Query(default=10, ge=1, le=10),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    synthesis = SynthesisService(db).run(user, horizon_days=horizon_days, limit=limit)
    acquisition = InformationAcquisitionService(db).materialize(user)
    return {**synthesis, "information_acquisition": acquisition}


@router.get("/users/{external_id}/candidates")
def list_candidates(
    external_id: str,
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(CandidateIntervention).filter(CandidateIntervention.user_id == user.id)
    if status:
        query = query.filter(CandidateIntervention.status == status)
    items = query.order_by(CandidateIntervention.updated_at.desc()).all()
    return [
        {
            "id": item.id,
            "candidate_key": item.candidate_key,
            "source_type": item.source_type,
            "source_ref": item.source_ref,
            "source_opportunity_id": item.source_opportunity_id,
            "hypothesis_ids": item.hypothesis_ids,
            "intent_ids": item.intent_ids,
            "name": item.name,
            "rationale": item.rationale,
            "intervention": item.intervention,
            "effects": item.effects,
            "assumptions": item.assumptions,
            "evidence": item.evidence,
            "confidence": item.confidence,
            "status": item.status,
            "rejection_reason": item.rejection_reason,
            "future_run_id": item.future_run_id,
            "scenario_id": item.scenario_id,
            "decision_status": item.decision_status,
            "surfaced_opportunity_id": item.surfaced_opportunity_id,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


@router.post("/candidates/{candidate_id}/requeue")
def requeue_candidate(candidate_id: int, db: Session = Depends(get_db)):
    item = (
        db.query(CandidateIntervention)
        .filter(CandidateIntervention.id == candidate_id)
        .one_or_none()
    )
    if not item:
        raise HTTPException(404, "candidate not found")
    if item.status == "ready_for_review":
        raise HTTPException(409, "ready candidate already passed the decision gate")
    item.status = "generated"
    item.rejection_reason = ""
    item.future_run_id = None
    item.scenario_id = None
    item.decision_status = ""
    item.updated_at = datetime.utcnow()
    db.commit()
    return {"id": item.id, "status": item.status}
