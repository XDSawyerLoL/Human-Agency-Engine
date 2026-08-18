from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, Opportunity, Outcome, PersonalMandate, User
from ..schemas import MandateOut, MandateUpsert, NotificationOut
from ..security import require_api_key

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


@router.get("/users/{external_id}/mandate", response_model=MandateOut)
def get_mandate(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    mandate = (
        db.query(PersonalMandate)
        .filter(PersonalMandate.user_id == user.id)
        .one_or_none()
    )
    if not mandate:
        raise HTTPException(404, "personal mandate not configured")
    return mandate


@router.put("/users/{external_id}/mandate", response_model=MandateOut)
def upsert_mandate(
    external_id: str,
    payload: MandateUpsert,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    mandate = (
        db.query(PersonalMandate)
        .filter(PersonalMandate.user_id == user.id)
        .one_or_none()
    )
    data = payload.model_dump()
    if mandate is None:
        mandate = PersonalMandate(user_id=user.id, **data)
        db.add(mandate)
    else:
        for key, value in data.items():
            setattr(mandate, key, value)
        mandate.version += 1
        mandate.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(mandate)
    return mandate


@router.get(
    "/users/{external_id}/notifications",
    response_model=list[NotificationOut],
)
def list_notifications(
    external_id: str,
    status: str | None = Query(default=None),
    include_suppressed: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if status:
        query = query.filter(Notification.status == status)
    elif not include_suppressed:
        query = query.filter(Notification.status != "suppressed")
    return query.order_by(Notification.created_at.desc()).all()


@router.put("/notifications/{notification_id}/status")
def update_notification_status(
    notification_id: int,
    status: str = Query(..., pattern="^(queued|delivered|dismissed)$"),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .one_or_none()
    )
    if not notification:
        raise HTTPException(404, "notification not found")
    if notification.status == "suppressed":
        raise HTTPException(409, "suppressed notification cannot be delivered")
    notification.status = status
    db.commit()
    return {"id": notification.id, "status": notification.status}


@router.get("/users/{external_id}/impact")
def impact_summary(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    opportunities = (
        db.query(Opportunity)
        .filter(Opportunity.user_id == user.id)
        .all()
    )
    opportunity_ids = [item.id for item in opportunities]
    outcomes = []
    if opportunity_ids:
        outcomes = (
            db.query(Outcome)
            .filter(Outcome.opportunity_id.in_(opportunity_ids))
            .all()
        )

    labeled = [item for item in outcomes if item.useful is not None]
    useful = sum(1 for item in labeled if item.useful is True)
    realized = sum(float(item.realized_value or 0.0) for item in outcomes)
    executed = sum(1 for item in outcomes if item.executed is True)
    accepted = sum(1 for item in outcomes if item.accepted is True)

    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .all()
    )
    surfaced = sum(1 for item in notifications if item.status != "suppressed")
    suppressed = sum(1 for item in notifications if item.status == "suppressed")

    return {
        "currency": user.currency,
        "opportunities_detected": len(opportunities),
        "opportunities_surfaced": surfaced,
        "opportunities_suppressed": suppressed,
        "feedback_labeled": len(labeled),
        "useful_count": useful,
        "useful_rate": round(useful / len(labeled), 4) if labeled else None,
        "accepted_count": accepted,
        "executed_count": executed,
        "realized_value": round(realized, 2),
    }
