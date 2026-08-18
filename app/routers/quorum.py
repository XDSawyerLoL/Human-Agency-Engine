from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..collective_models import CollectiveIntentMembership
from ..collective_offer_models import CollectiveMarketOffer
from ..db import get_db
from ..models import User
from ..quorum_models import CollectiveConditionalCommitment
from ..quorum_schemas import CollectiveConditionalCommit, CollectiveConditionalRevoke
from ..security import require_api_key
from ..services.quorum import CollectiveQuorumService

router = APIRouter(
    prefix="/collective-quorum",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _commitment_out(item: CollectiveConditionalCommitment, db: Session) -> dict:
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.id == item.offer_db_id).one()
    membership = (
        db.query(CollectiveIntentMembership)
        .filter(CollectiveIntentMembership.id == item.membership_id)
        .one_or_none()
    )
    return {
        "commitment_id": item.commitment_id,
        "offer_id": offer.offer_id,
        "membership_id": membership.membership_id if membership else None,
        "quantity": item.quantity,
        "offer_hash": item.offer_hash,
        "conditions_hash": item.conditions_hash,
        "status": item.status,
        "created_at": item.created_at,
        "revoked_at": item.revoked_at,
        "conditional_only": True,
        "payment_created": False,
        "order_created": False,
        "shared_with_responder": False,
    }


@router.post("/users/{external_id}/commit")
def create_conditional_commitment(
    external_id: str,
    payload: CollectiveConditionalCommit,
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
        commitment = CollectiveQuorumService(db).commit(user, membership, offer, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _commitment_out(commitment, db)


@router.post("/users/{external_id}/commitments/{commitment_id}/revoke")
def revoke_conditional_commitment(
    external_id: str,
    commitment_id: str,
    payload: CollectiveConditionalRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    commitment = (
        db.query(CollectiveConditionalCommitment)
        .filter(CollectiveConditionalCommitment.commitment_id == commitment_id)
        .one_or_none()
    )
    if not commitment:
        raise HTTPException(404, "conditional commitment not found")
    try:
        commitment = CollectiveQuorumService(db).revoke(user, commitment, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _commitment_out(commitment, db)


@router.get("/users/{external_id}/commitments")
def list_user_commitments(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(CollectiveConditionalCommitment)
        .filter(CollectiveConditionalCommitment.user_id == user.id)
        .order_by(CollectiveConditionalCommitment.created_at.desc())
        .all()
    )
    return {
        "commitments": [_commitment_out(item, db) for item in rows],
        "scope": "self_only",
        "shared_with_responders": False,
        "payment_created": False,
        "order_created": False,
    }


@router.get("/offers/{offer_id}")
def get_public_quorum(offer_id: str, db: Session = Depends(get_db)):
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.offer_id == offer_id).one_or_none()
    if not offer:
        raise HTTPException(404, "collective offer not found")
    return CollectiveQuorumService(db).quorum(offer)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
