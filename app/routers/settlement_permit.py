from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.settlement_permit import SettlementPermitService
from ..settlement_permit_models import PseudonymousSettlementPermit
from ..settlement_permit_schemas import (
    SettlementPermitConsume,
    SettlementPermitIssue,
    SettlementPermitRevoke,
    SettlementPermitVerify,
)

router = APIRouter(
    prefix="/settlement-permits",
    dependencies=[Depends(require_api_key)],
)
public_router = APIRouter(prefix="/settlement-permits")


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _permit_out(item: PseudonymousSettlementPermit) -> dict:
    return {
        "permit_id": item.permit_id,
        "subject_ref": item.subject_ref,
        "audience": item.audience,
        "readiness_hash": item.readiness_hash,
        "allocation_set_hash": item.allocation_set_hash,
        "accepted_set_hash": item.accepted_set_hash,
        "offer_hash": item.offer_hash,
        "decision_hash": item.decision_hash,
        "conditions_hash": item.conditions_hash,
        "mandate_version": item.mandate_version,
        "allocated_quantity": item.allocated_quantity,
        "unit_price": item.unit_price,
        "currency": item.currency,
        "exact_total_amount": item.exact_total_amount,
        "status": item.status,
        "use_count": item.use_count,
        "issued_at": item.issued_at,
        "expires_at": item.expires_at,
        "consumed_at": item.consumed_at,
        "revoked_at": item.revoked_at,
        "identity_disclosed": False,
        "address_disclosed": False,
        "payment_instrument_disclosed": False,
        "bearer_token_stored_in_database": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}")
def issue_settlement_permit(
    external_id: str,
    payload: SettlementPermitIssue,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        permit, proof = SettlementPermitService(db).issue(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "permit": _permit_out(permit),
        "proof": proof,
        "capability": "prepare_settlement",
        "one_time": True,
        "identity_disclosed": False,
        "address_disclosed": False,
        "payment_instrument_disclosed": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@public_router.post("/verify")
def verify_settlement_permit(payload: SettlementPermitVerify, db: Session = Depends(get_db)):
    try:
        return SettlementPermitService(db).verify(payload.token, payload.audience)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/consume")
def consume_settlement_permit(payload: SettlementPermitConsume, db: Session = Depends(get_db)):
    try:
        use = SettlementPermitService(db).consume(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "consumed": True,
        "request_id": use.request_id,
        "audience": use.audience,
        "effect": "prepare_settlement_only",
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}/{permit_id}/revoke")
def revoke_settlement_permit(
    external_id: str,
    permit_id: str,
    payload: SettlementPermitRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    permit = (
        db.query(PseudonymousSettlementPermit)
        .filter(PseudonymousSettlementPermit.permit_id == permit_id)
        .one_or_none()
    )
    if not permit:
        raise HTTPException(404, "settlement permit not found")
    try:
        permit = SettlementPermitService(db).revoke(user, permit, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _permit_out(permit)


@router.get("/users/{external_id}")
def list_user_settlement_permits(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(PseudonymousSettlementPermit)
        .filter(PseudonymousSettlementPermit.user_id == user.id)
        .order_by(PseudonymousSettlementPermit.issued_at.desc())
        .all()
    )
    return {
        "permits": [_permit_out(item) for item in rows],
        "scope": "self_only",
        "bearer_tokens_included": False,
        "private_keys_included": False,
        "identity_disclosed": False,
        "address_disclosed": False,
        "payment_instrument_disclosed": False,
    }
