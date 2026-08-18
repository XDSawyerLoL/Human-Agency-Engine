from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..payment_intent_models import PaymentIntentCapability
from ..payment_intent_schemas import (
    PaymentIntentConsume,
    PaymentIntentIssue,
    PaymentIntentPreview,
    PaymentIntentRevoke,
    PaymentIntentVerify,
)
from ..security import require_api_key
from ..services.payment_intent import PaymentIntentCapabilityService

router = APIRouter(prefix="/payment-intents", dependencies=[Depends(require_api_key)])
public_router = APIRouter(prefix="/payment-intents")


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _out(item: PaymentIntentCapability) -> dict:
    return {
        "capability_id": item.capability_id,
        "subject_ref": item.subject_ref,
        "audience": item.audience,
        "payment_terms_hash": item.payment_terms_hash,
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
        "debit_allowed": False,
        "capture_allowed": False,
        "funds_movement_allowed": False,
        "payment_instrument_access": False,
        "bearer_token_stored_in_database": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}/preview")
def preview_payment_intent(
    external_id: str,
    payload: PaymentIntentPreview,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return PaymentIntentCapabilityService(db).preview(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/users/{external_id}")
def issue_payment_intent(
    external_id: str,
    payload: PaymentIntentIssue,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        capability, proof = PaymentIntentCapabilityService(db).issue(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "capability": _out(capability),
        "proof": proof,
        "one_time": True,
        "effect": "prepare_payment_intent_only",
        "debit_allowed": False,
        "capture_allowed": False,
        "funds_movement_allowed": False,
        "payment_instrument_access": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@public_router.post("/verify")
def verify_payment_intent(
    payload: PaymentIntentVerify,
    db: Session = Depends(get_db),
):
    try:
        return PaymentIntentCapabilityService(db).verify(payload.token, payload.audience)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/consume")
def consume_payment_intent(
    payload: PaymentIntentConsume,
    db: Session = Depends(get_db),
):
    try:
        use = PaymentIntentCapabilityService(db).consume(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "consumed": True,
        "request_id": use.request_id,
        "audience": use.audience,
        "effect": "prepare_payment_intent_only",
        "debit_allowed": False,
        "capture_allowed": False,
        "funds_movement_allowed": False,
        "payment_instrument_access": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}/{capability_id}/revoke")
def revoke_payment_intent(
    external_id: str,
    capability_id: str,
    payload: PaymentIntentRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    capability = (
        db.query(PaymentIntentCapability)
        .filter(PaymentIntentCapability.capability_id == capability_id)
        .one_or_none()
    )
    if not capability:
        raise HTTPException(404, "payment-intent capability not found")
    try:
        capability = PaymentIntentCapabilityService(db).revoke(
            user,
            capability,
            payload.confirm,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _out(capability)


@router.get("/users/{external_id}")
def list_user_payment_intents(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(PaymentIntentCapability)
        .filter(PaymentIntentCapability.user_id == user.id)
        .order_by(PaymentIntentCapability.issued_at.desc())
        .all()
    )
    return {
        "capabilities": [_out(item) for item in rows],
        "scope": "self_only",
        "bearer_tokens_included": False,
        "payment_instruments_included": False,
        "debit_allowed": False,
        "funds_movement_allowed": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
agency_router.include_router(public_router)
