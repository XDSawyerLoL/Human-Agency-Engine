from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentCohort, CollectiveIntentMembership
from ..collective_schemas import CollectiveIntentJoin, CollectiveIntentLeave
from ..db import get_db
from ..market_models import PrivateIntentEnvelope
from ..models import User
from ..security import require_api_key
from ..services.collective import CollectiveIntentService

router = APIRouter(
    prefix="/collective",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _membership_out(item: CollectiveIntentMembership, db: Session) -> dict:
    cohort = db.query(CollectiveIntentCohort).filter(CollectiveIntentCohort.id == item.cohort_id).one()
    envelope = db.query(PrivateIntentEnvelope).filter(PrivateIntentEnvelope.id == item.envelope_db_id).one_or_none()
    return {
        "membership_id": item.membership_id,
        "cohort_key": cohort.cohort_key,
        "envelope_id": envelope.envelope_id if envelope else None,
        "status": item.status,
        "joined_at": item.joined_at,
        "left_at": item.left_at,
        "minimum_cohort_size": cohort.minimum_cohort_size,
        "other_member_count_included": False,
        "other_member_identities_included": False,
    }


@router.post("/users/{external_id}/join")
def join_collective_intent(
    external_id: str,
    payload: CollectiveIntentJoin,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == payload.envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "private intent envelope not found")
    try:
        membership = CollectiveIntentService(db).join(user, envelope, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _membership_out(membership, db)


@router.post("/users/{external_id}/memberships/{membership_id}/leave")
def leave_collective_intent(
    external_id: str,
    membership_id: str,
    payload: CollectiveIntentLeave,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    membership = (
        db.query(CollectiveIntentMembership)
        .filter(CollectiveIntentMembership.membership_id == membership_id)
        .one_or_none()
    )
    if not membership:
        raise HTTPException(404, "collective membership not found")
    try:
        membership = CollectiveIntentService(db).leave(user, membership, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _membership_out(membership, db)


@router.get("/users/{external_id}/memberships")
def list_user_collective_memberships(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(CollectiveIntentMembership)
        .filter(CollectiveIntentMembership.user_id == user.id)
        .order_by(CollectiveIntentMembership.joined_at.desc())
        .all()
    )
    return {
        "memberships": [_membership_out(item, db) for item in rows],
        "scope": "self_only",
        "other_member_identities_included": False,
    }


@router.get("/cohorts/{cohort_key}")
def get_collective_aggregate(cohort_key: str, db: Session = Depends(get_db)):
    cohort = (
        db.query(CollectiveIntentCohort)
        .filter(CollectiveIntentCohort.cohort_key == cohort_key)
        .one_or_none()
    )
    if not cohort:
        raise HTTPException(404, "collective cohort not found")
    return CollectiveIntentService(db).aggregate(cohort)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
