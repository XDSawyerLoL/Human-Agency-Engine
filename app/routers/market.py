from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..market_models import MarketOffer, PrivateIntentEnvelope
from ..market_schemas import MarketOfferSubmit, PrivateIntentOpen, PrivateIntentRevoke
from ..models import User
from ..security import require_api_key
from ..services.market import PrivateIntentMarketService, public_envelope

router = APIRouter(
    prefix="/market",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _offer_out(item: MarketOffer) -> dict:
    return {
        "offer_id": item.offer_id,
        "responder_id": item.responder_id,
        "responder_label": item.responder_label,
        "offer_hash": item.offer_hash,
        "payload": item.payload,
        "eligibility": item.eligibility,
        "status": item.status,
        "identity_assurance": "key_possession_only",
        "created_at": item.created_at,
    }


@router.post("/users/{external_id}/intents")
def open_private_intent(
    external_id: str,
    payload: PrivateIntentOpen,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        envelope = PrivateIntentMarketService(db).open(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return public_envelope(envelope)


@router.get("/users/{external_id}/intents")
def list_private_intents(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.user_id == user.id)
        .order_by(PrivateIntentEnvelope.created_at.desc())
        .all()
    )
    return [public_envelope(item) for item in rows]


@router.post("/users/{external_id}/intents/{envelope_id}/revoke")
def revoke_private_intent(
    external_id: str,
    envelope_id: str,
    payload: PrivateIntentRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "market intent not found")
    try:
        envelope = PrivateIntentMarketService(db).revoke(user, envelope, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return public_envelope(envelope)


@router.get("/intents/{envelope_id}")
def get_private_intent(envelope_id: str, db: Session = Depends(get_db)):
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "market intent not found")
    return public_envelope(envelope)


@router.post("/intents/{envelope_id}/offers")
def submit_market_offer(
    envelope_id: str,
    payload: MarketOfferSubmit,
    db: Session = Depends(get_db),
):
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "market intent not found")
    try:
        offer = PrivateIntentMarketService(db).submit_offer(envelope, payload)
    except ValueError as exc:
        status = 409 if "replayed" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _offer_out(offer)


@router.get("/intents/{envelope_id}/offers")
def list_market_offers(envelope_id: str, db: Session = Depends(get_db)):
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "market intent not found")
    rows = (
        db.query(MarketOffer)
        .filter(MarketOffer.envelope_db_id == envelope.id)
        .order_by(MarketOffer.created_at.asc())
        .all()
    )
    return [_offer_out(item) for item in rows]


@router.get("/intents/{envelope_id}/ranked")
def rank_market_offers(envelope_id: str, db: Session = Depends(get_db)):
    envelope = (
        db.query(PrivateIntentEnvelope)
        .filter(PrivateIntentEnvelope.envelope_id == envelope_id)
        .one_or_none()
    )
    if not envelope:
        raise HTTPException(404, "market intent not found")
    try:
        return PrivateIntentMarketService(db).rank(envelope)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
