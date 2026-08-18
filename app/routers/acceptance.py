from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..acceptance_models import CollectiveAllocationDecision
from ..acceptance_schemas import AllocationAcceptanceRevoke, AllocationDecisionCreate
from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.acceptance import AllocationAcceptanceService

router = APIRouter(
    prefix="/collective-acceptance",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _out(item: CollectiveAllocationDecision) -> dict:
    return {
        "decision_id": item.decision_id,
        "decision": item.decision,
        "allocation_set_hash": item.allocation_set_hash,
        "offer_hash": item.offer_hash,
        "conditions_hash": item.conditions_hash,
        "envelope_hash": item.envelope_hash,
        "allocated_quantity": item.allocated_quantity,
        "unit_price": item.unit_price,
        "currency": item.currency,
        "exact_total_amount": item.exact_total_amount,
        "decision_hash": item.decision_hash,
        "decided_at": item.decided_at,
        "revoked_at": item.revoked_at,
        "effective_acceptance": item.decision == "accepted" and item.revoked_at is None,
        "shared_with_responder": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}/accept")
def accept_allocation(
    external_id: str,
    payload: AllocationDecisionCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        row = AllocationAcceptanceService(db).decide(
            user,
            payload.allocation_entry_id,
            "accepted",
            payload.confirm,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(row)


@router.post("/users/{external_id}/reject")
def reject_allocation(
    external_id: str,
    payload: AllocationDecisionCreate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        row = AllocationAcceptanceService(db).decide(
            user,
            payload.allocation_entry_id,
            "rejected",
            payload.confirm,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(row)


@router.post("/users/{external_id}/decisions/{decision_id}/revoke")
def revoke_allocation_acceptance(
    external_id: str,
    decision_id: str,
    payload: AllocationAcceptanceRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    row = (
        db.query(CollectiveAllocationDecision)
        .filter(CollectiveAllocationDecision.decision_id == decision_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "allocation decision not found")
    try:
        row = AllocationAcceptanceService(db).revoke_acceptance(user, row, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(row)


@router.get("/users/{external_id}")
def list_user_allocation_decisions(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(CollectiveAllocationDecision)
        .filter(CollectiveAllocationDecision.user_id == user.id)
        .order_by(CollectiveAllocationDecision.decided_at.desc())
        .all()
    )
    return {
        "decisions": [_out(item) for item in rows],
        "scope": "self_only",
        "shared_with_responders": False,
        "payment_created": False,
        "order_created": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
