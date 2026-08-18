from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentMembership
from ..collective_offer_models import (
    CollectiveMarketOffer,
    CollectiveMarketWindow,
    CollectiveOfferEvaluation,
)
from ..collective_offer_schemas import (
    CollectiveMarketOpen,
    CollectiveOfferEvaluate,
    CollectiveOfferSubmit,
)
from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.collective_offers import (
    CollectiveOfferService,
    collective_offer_signed_payload,
    public_collective_window,
)

router = APIRouter(
    prefix="/collective-market",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _offer_out(item: CollectiveMarketOffer) -> dict:
    return {
        "offer_id": item.offer_id,
        "responder_id": item.responder_id,
        "responder_label": item.responder_label,
        "offer_hash": item.offer_hash,
        "payload": item.payload,
        "group_eligibility": item.group_eligibility,
        "status": item.status,
        "valid_until": item.valid_until,
        "identity_assurance": "key_possession_only",
        "individual_evaluations_included": False,
        "member_identities_included": False,
        "created_at": item.created_at,
    }


def _evaluation_out(item: CollectiveOfferEvaluation, db: Session) -> dict:
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.id == item.offer_db_id).one()
    return {
        "evaluation_id": item.evaluation_id,
        "offer_id": offer.offer_id,
        "provisional_eligible": item.provisional_eligible,
        "reasons": item.reasons,
        "score_components": item.score_components,
        "fiduciary_score": item.fiduciary_score,
        "commission_excluded_from_ranking": item.commission_excluded,
        "collective_minimum_not_committed": True,
        "shared_with_responder": False,
        "created_at": item.created_at,
    }


@router.post("/windows")
def open_collective_market_window(payload: CollectiveMarketOpen, db: Session = Depends(get_db)):
    try:
        window = CollectiveOfferService(db).open_window(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return public_collective_window(window)


@router.get("/windows/{window_id}")
def get_collective_market_window(window_id: str, db: Session = Depends(get_db)):
    window = db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.window_id == window_id).one_or_none()
    if not window:
        raise HTTPException(404, "collective market window not found")
    return public_collective_window(window)


@router.post("/windows/{window_id}/offers")
def submit_collective_offer(
    window_id: str,
    payload: CollectiveOfferSubmit,
    db: Session = Depends(get_db),
):
    window = db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.window_id == window_id).one_or_none()
    if not window:
        raise HTTPException(404, "collective market window not found")
    try:
        offer = CollectiveOfferService(db).submit_offer(window, payload)
    except ValueError as exc:
        status = 409 if "replayed" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _offer_out(offer)


@router.get("/windows/{window_id}/offers")
def list_collective_offers(window_id: str, db: Session = Depends(get_db)):
    window = db.query(CollectiveMarketWindow).filter(CollectiveMarketWindow.window_id == window_id).one_or_none()
    if not window:
        raise HTTPException(404, "collective market window not found")
    rows = (
        db.query(CollectiveMarketOffer)
        .filter(CollectiveMarketOffer.window_id == window.id)
        .order_by(CollectiveMarketOffer.created_at.asc())
        .all()
    )
    return {
        "window": public_collective_window(window),
        "offers": [_offer_out(item) for item in rows],
        "individual_evaluations_included": False,
        "member_identities_included": False,
    }


@router.post("/users/{external_id}/evaluate")
def evaluate_collective_offer_for_user(
    external_id: str,
    payload: CollectiveOfferEvaluate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    membership = (
        db.query(CollectiveIntentMembership)
        .filter(CollectiveIntentMembership.membership_id == payload.membership_id)
        .one_or_none()
    )
    if not membership:
        raise HTTPException(404, "collective membership not found")
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.offer_id == payload.offer_id).one_or_none()
    if not offer:
        raise HTTPException(404, "collective offer not found")
    try:
        evaluation = CollectiveOfferService(db).evaluate_for_user(user, membership, offer)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _evaluation_out(evaluation, db)


@router.get("/users/{external_id}/evaluations")
def list_private_collective_offer_evaluations(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(CollectiveOfferEvaluation)
        .filter(CollectiveOfferEvaluation.user_id == user.id)
        .order_by(CollectiveOfferEvaluation.created_at.desc())
        .all()
    )
    return {
        "evaluations": [_evaluation_out(item, db) for item in rows],
        "scope": "self_only",
        "shared_with_responders": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
