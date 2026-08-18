from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Intent, StateFact, User
from ..schemas import IntentUpdate, StateFactCreate, StateFactOut
from ..security import require_api_key
from ..services.world_model import WorldModelService
from ..world_schemas import EventCreate

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


@router.post("/users/{external_id}/state/facts", response_model=StateFactOut)
def add_state_fact(
    external_id: str,
    payload: StateFactCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    data = payload.model_dump(exclude={"replace_current"}, exclude_none=True)
    observed_at = data.get("observed_at", datetime.utcnow())
    data["observed_at"] = observed_at
    expires_at = data.get("expires_at")
    if expires_at is not None and expires_at <= observed_at:
        raise HTTPException(400, "expires_at must be after observed_at")

    if payload.replace_current:
        (
            db.query(StateFact)
            .filter(
                StateFact.user_id == user.id,
                StateFact.domain == payload.domain,
                StateFact.key == payload.key,
                StateFact.superseded == False,  # noqa: E712
            )
            .update({StateFact.superseded: True}, synchronize_session=False)
        )

    fact = StateFact(user_id=user.id, **data)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="state.fact_observed",
            source=fact.source,
            subject_type="state_fact",
            subject_id=str(fact.id),
            payload={
                "domain": fact.domain,
                "key": fact.key,
                "confidence": fact.confidence,
                "sensitivity": fact.sensitivity,
                "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
            },
            confidence=fact.confidence,
            occurred_at=fact.observed_at,
        ),
    )
    return fact


@router.get("/users/{external_id}/state/facts", response_model=list[StateFactOut])
def list_state_facts(
    external_id: str,
    domain: str | None = Query(default=None),
    include_history: bool = Query(default=False),
    include_expired: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(StateFact).filter(StateFact.user_id == user.id)
    if domain:
        query = query.filter(StateFact.domain == domain)
    if not include_history:
        query = query.filter(StateFact.superseded == False)  # noqa: E712
    if not include_expired:
        now = datetime.utcnow()
        query = query.filter(or_(StateFact.expires_at.is_(None), StateFact.expires_at > now))
    return query.order_by(StateFact.observed_at.desc()).all()


@router.get("/users/{external_id}/state")
def current_state(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    now = datetime.utcnow()
    facts = (
        db.query(StateFact)
        .filter(
            StateFact.user_id == user.id,
            StateFact.superseded == False,  # noqa: E712
            or_(StateFact.expires_at.is_(None), StateFact.expires_at > now),
        )
        .all()
    )

    selected: dict[tuple[str, str], StateFact] = {}
    for fact in facts:
        identity = (fact.domain, fact.key)
        current = selected.get(identity)
        if current is None or (fact.confidence, fact.observed_at) > (current.confidence, current.observed_at):
            selected[identity] = fact

    domains: dict[str, dict] = {}
    for (domain, key), fact in sorted(selected.items()):
        domains.setdefault(domain, {})[key] = {
            "value": fact.value,
            "source": fact.source,
            "confidence": fact.confidence,
            "sensitivity": fact.sensitivity,
            "observed_at": fact.observed_at,
            "expires_at": fact.expires_at,
            "fact_id": fact.id,
        }

    return {
        "external_id": user.external_id,
        "as_of": now,
        "fact_count": len(selected),
        "domains": domains,
    }


@router.post("/state/facts/{fact_id}/supersede")
def supersede_state_fact(fact_id: int, db: Session = Depends(get_db)):
    fact = db.query(StateFact).filter(StateFact.id == fact_id).one_or_none()
    if not fact:
        raise HTTPException(404, "state fact not found")
    fact.superseded = True
    db.commit()
    user = db.query(User).filter(User.id == fact.user_id).one()
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="state.fact_superseded",
            source="user",
            subject_type="state_fact",
            subject_id=str(fact.id),
            payload={"domain": fact.domain, "key": fact.key},
        ),
    )
    return {"id": fact.id, "superseded": True}


@router.get("/users/{external_id}/intents")
def list_intents(external_id: str, active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    query = db.query(Intent).filter(Intent.user_id == user.id)
    if active_only:
        query = query.filter(Intent.active == True)  # noqa: E712
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "statement": item.statement,
            "target": item.target,
            "priority": item.priority,
            "active": item.active,
            "created_at": item.created_at,
        }
        for item in query.order_by(Intent.priority.desc(), Intent.created_at.desc()).all()
    ]


@router.patch("/intents/{intent_id}")
def update_intent(intent_id: int, payload: IntentUpdate, db: Session = Depends(get_db)):
    intent = db.query(Intent).filter(Intent.id == intent_id).one_or_none()
    if not intent:
        raise HTTPException(404, "intent not found")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(intent, key, value)
    db.commit()
    db.refresh(intent)
    user = db.query(User).filter(User.id == intent.user_id).one()
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="intent.updated",
            source="user",
            subject_type="intent",
            subject_id=str(intent.id),
            payload={"changed_fields": sorted(changes.keys()), "priority": intent.priority, "active": intent.active},
        ),
    )
    return {
        "id": intent.id,
        "kind": intent.kind,
        "statement": intent.statement,
        "target": intent.target,
        "priority": intent.priority,
        "active": intent.active,
    }
