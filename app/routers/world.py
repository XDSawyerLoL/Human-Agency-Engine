from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.world_model import WorldModelService
from ..world_models import Experiment, HypothesisEvidence, WorldEvent, WorldHypothesis
from ..world_schemas import (
    EventCreate,
    EvidenceCreate,
    ExperimentAuthorize,
    ExperimentCreate,
    ExperimentObservationCreate,
    HypothesisCreate,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _experiment_or_404(db: Session, experiment_id: int) -> Experiment:
    item = db.query(Experiment).filter(Experiment.id == experiment_id).one_or_none()
    if not item:
        raise HTTPException(404, "experiment not found")
    return item


@router.post("/users/{external_id}/world/events")
def append_event(external_id: str, payload: EventCreate, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    event = WorldModelService(db).append_event(user, payload)
    return {
        "id": event.id,
        "event_type": event.event_type,
        "event_hash": event.event_hash,
        "previous_hash": event.previous_hash,
        "occurred_at": event.occurred_at,
    }


@router.get("/users/{external_id}/world/events")
def list_events(
    external_id: str,
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(WorldEvent).filter(WorldEvent.user_id == user.id)
    if event_type:
        query = query.filter(WorldEvent.event_type == event_type)
    events = query.order_by(WorldEvent.id.desc()).limit(limit).all()
    return [
        {
            "id": item.id,
            "event_type": item.event_type,
            "source": item.source,
            "subject_type": item.subject_type,
            "subject_id": item.subject_id,
            "payload": item.payload,
            "confidence": item.confidence,
            "occurred_at": item.occurred_at,
            "recorded_at": item.recorded_at,
            "causation_id": item.causation_id,
            "correlation_id": item.correlation_id,
            "previous_hash": item.previous_hash,
            "event_hash": item.event_hash,
        }
        for item in events
    ]


@router.get("/users/{external_id}/world/integrity")
def verify_world_integrity(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return WorldModelService(db).verify_chain(user)


@router.post("/users/{external_id}/world/hypotheses")
def create_hypothesis(external_id: str, payload: HypothesisCreate, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    hypothesis = WorldModelService(db).create_hypothesis(user, payload)
    return {
        "id": hypothesis.id,
        "name": hypothesis.name,
        "claim_level": hypothesis.claim_level,
        "confidence": hypothesis.confidence,
    }


@router.get("/users/{external_id}/world/hypotheses")
def list_hypotheses(external_id: str, active_only: bool = True, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    query = db.query(WorldHypothesis).filter(WorldHypothesis.user_id == user.id)
    if active_only:
        query = query.filter(WorldHypothesis.status == "active")
    items = query.order_by(WorldHypothesis.updated_at.desc()).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "cause_pattern": item.cause_pattern,
            "effect_pattern": item.effect_pattern,
            "context": item.context,
            "direction": item.direction,
            "claim_level": item.claim_level,
            "confidence": item.confidence,
            "support_count": item.support_count,
            "contradiction_count": item.contradiction_count,
            "inconclusive_count": item.inconclusive_count,
            "status": item.status,
            "provenance": item.provenance,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


@router.post("/world/hypotheses/{hypothesis_id}/evidence")
def add_hypothesis_evidence(hypothesis_id: int, external_id: str, payload: EvidenceCreate, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    hypothesis = (
        db.query(WorldHypothesis)
        .filter(WorldHypothesis.id == hypothesis_id)
        .one_or_none()
    )
    if not hypothesis:
        raise HTTPException(404, "hypothesis not found")
    try:
        evidence = WorldModelService(db).add_evidence(user, hypothesis, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.refresh(hypothesis)
    return {
        "evidence_id": evidence.id,
        "hypothesis_id": hypothesis.id,
        "claim_level": hypothesis.claim_level,
        "confidence": hypothesis.confidence,
        "support_count": hypothesis.support_count,
        "contradiction_count": hypothesis.contradiction_count,
        "inconclusive_count": hypothesis.inconclusive_count,
    }


@router.get("/world/hypotheses/{hypothesis_id}/evidence")
def list_hypothesis_evidence(hypothesis_id: int, db: Session = Depends(get_db)):
    hypothesis = db.query(WorldHypothesis).filter(WorldHypothesis.id == hypothesis_id).one_or_none()
    if not hypothesis:
        raise HTTPException(404, "hypothesis not found")
    items = (
        db.query(HypothesisEvidence)
        .filter(HypothesisEvidence.hypothesis_id == hypothesis.id)
        .order_by(HypothesisEvidence.created_at.asc())
        .all()
    )
    return [
        {
            "id": item.id,
            "event_id": item.event_id,
            "experiment_id": item.experiment_id,
            "observation_id": item.observation_id,
            "verdict": item.verdict,
            "quality": item.quality,
            "notes": item.notes,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/users/{external_id}/experiments")
def create_experiment(external_id: str, payload: ExperimentCreate, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    try:
        item = WorldModelService(db).create_experiment(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "id": item.id,
        "title": item.title,
        "reversible": item.reversible,
        "authorization_status": item.authorization_status,
        "execution_status": item.execution_status,
    }


@router.get("/users/{external_id}/experiments")
def list_experiments(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    items = db.query(Experiment).filter(Experiment.user_id == user.id).order_by(Experiment.created_at.desc()).all()
    return [
        {
            "id": item.id,
            "scenario_id": item.scenario_id,
            "hypothesis_id": item.hypothesis_id,
            "title": item.title,
            "intervention": item.intervention,
            "expected_effects": item.expected_effects,
            "stop_conditions": item.stop_conditions,
            "rollback_plan": item.rollback_plan,
            "reversible": item.reversible,
            "authorization_status": item.authorization_status,
            "execution_status": item.execution_status,
            "authorized_at": item.authorized_at,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
        }
        for item in items
    ]


@router.post("/experiments/{experiment_id}/authorize")
def authorize_experiment(experiment_id: int, payload: ExperimentAuthorize, db: Session = Depends(get_db)):
    item = _experiment_or_404(db, experiment_id)
    user = db.query(User).filter(User.id == item.user_id).one()
    try:
        item = WorldModelService(db).authorize_experiment(
            user,
            item,
            confirm=payload.confirm,
            irreversible_ack=payload.irreversible_ack,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": item.id, "authorization_status": item.authorization_status, "authorized_at": item.authorized_at}


@router.post("/experiments/{experiment_id}/start")
def start_experiment(experiment_id: int, db: Session = Depends(get_db)):
    item = _experiment_or_404(db, experiment_id)
    user = db.query(User).filter(User.id == item.user_id).one()
    try:
        item = WorldModelService(db).start_experiment(user, item)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": item.id, "execution_status": item.execution_status, "started_at": item.started_at}


@router.post("/experiments/{experiment_id}/observations")
def record_experiment_observation(experiment_id: int, payload: ExperimentObservationCreate, db: Session = Depends(get_db)):
    item = _experiment_or_404(db, experiment_id)
    user = db.query(User).filter(User.id == item.user_id).one()
    observation = WorldModelService(db).record_observation(user, item, payload)
    hypothesis = None
    if item.hypothesis_id is not None:
        hypothesis = db.query(WorldHypothesis).filter(WorldHypothesis.id == item.hypothesis_id).one_or_none()
    return {
        "id": observation.id,
        "experiment_id": observation.experiment_id,
        "verdict": observation.verdict,
        "quality": observation.quality,
        "hypothesis": None if hypothesis is None else {
            "id": hypothesis.id,
            "claim_level": hypothesis.claim_level,
            "confidence": hypothesis.confidence,
            "support_count": hypothesis.support_count,
            "contradiction_count": hypothesis.contradiction_count,
        },
    }


@router.post("/experiments/{experiment_id}/complete")
def complete_experiment(experiment_id: int, db: Session = Depends(get_db)):
    item = _experiment_or_404(db, experiment_id)
    user = db.query(User).filter(User.id == item.user_id).one()
    try:
        item = WorldModelService(db).complete_experiment(user, item)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": item.id, "execution_status": item.execution_status, "completed_at": item.completed_at}


@router.post("/experiments/{experiment_id}/rollback")
def rollback_experiment(experiment_id: int, db: Session = Depends(get_db)):
    item = _experiment_or_404(db, experiment_id)
    user = db.query(User).filter(User.id == item.user_id).one()
    try:
        item = WorldModelService(db).rollback_experiment(user, item)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": item.id, "execution_status": item.execution_status, "rollback_plan": item.rollback_plan}
