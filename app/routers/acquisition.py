from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..acquisition_models import InformationNeed
from ..acquisition_schemas import InformationResolution, InformationWaive
from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.acquisition import InformationAcquisitionService

router = APIRouter(dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _need_or_404(db: Session, user: User, need_id: int) -> InformationNeed:
    need = (
        db.query(InformationNeed)
        .filter(InformationNeed.id == need_id, InformationNeed.user_id == user.id)
        .one_or_none()
    )
    if not need:
        raise HTTPException(404, "information need not found")
    return need


def _out(item: InformationNeed) -> dict:
    return {
        "id": item.id,
        "candidate_id": item.candidate_id,
        "future_run_id": item.future_run_id,
        "scenario_id": item.scenario_id,
        "need_type": item.need_type,
        "question": item.question,
        "reason": item.reason,
        "priority": item.priority,
        "acquisition_mode": item.acquisition_mode,
        "preferred_sources": item.preferred_sources,
        "sensitivity": item.sensitivity,
        "blocks_candidate": item.blocks_candidate,
        "status": item.status,
        "resolution": item.resolution,
        "resolution_source": item.resolution_source,
        "resolution_provenance": item.resolution_provenance,
        "resolution_confidence": item.resolution_confidence,
        "ask_count": item.ask_count,
        "last_asked_at": item.last_asked_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "resolved_at": item.resolved_at,
    }


@router.post("/users/{external_id}/information/materialize")
def materialize_information_needs(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return InformationAcquisitionService(db).materialize(user)


@router.get("/users/{external_id}/information/needs")
def list_information_needs(
    external_id: str,
    status: str | None = Query(default=None),
    candidate_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(InformationNeed).filter(InformationNeed.user_id == user.id)
    if status:
        query = query.filter(InformationNeed.status == status)
    if candidate_id is not None:
        query = query.filter(InformationNeed.candidate_id == candidate_id)
    items = query.order_by(InformationNeed.created_at.desc()).all()
    return [_out(item) for item in items]


@router.post("/users/{external_id}/information/next-questions")
def next_information_questions(
    external_id: str,
    requested: int = Query(default=5, ge=0, le=10),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    service = InformationAcquisitionService(db)
    service.auto_resolve_from_known_state(user)
    return [_out(item) for item in service.claim_user_questions(user, requested=requested)]


@router.put("/users/{external_id}/information/needs/{need_id}/resolve")
def resolve_information_need(
    external_id: str,
    need_id: int,
    payload: InformationResolution,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    need = _need_or_404(db, user, need_id)
    try:
        resolved = InformationAcquisitionService(db).resolve(user, need, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(resolved)


@router.put("/users/{external_id}/information/needs/{need_id}/waive")
def waive_information_need(
    external_id: str,
    need_id: int,
    payload: InformationWaive,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    need = _need_or_404(db, user, need_id)
    try:
        waived = InformationAcquisitionService(db).waive(user, need, payload.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(waived)
