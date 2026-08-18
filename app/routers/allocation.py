from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..allocation_models import CollectiveAllocationRound, CollectivePrivateAllocation
from ..allocation_schemas import CollectiveAllocationCreate
from ..db import get_db
from ..models import User
from ..quorum_models import CollectiveConditionalCommitment
from ..collective_offer_models import CollectiveMarketOffer
from ..security import require_api_key
from ..services.allocation import CollectiveAllocationService

router = APIRouter(
    prefix="/collective-allocation",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _private_out(item: CollectivePrivateAllocation, db: Session) -> dict:
    commitment = (
        db.query(CollectiveConditionalCommitment)
        .filter(CollectiveConditionalCommitment.id == item.commitment_id)
        .one()
    )
    round_row = (
        db.query(CollectiveAllocationRound)
        .filter(CollectiveAllocationRound.id == item.allocation_round_id)
        .one()
    )
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.id == round_row.offer_db_id).one()
    return {
        "allocation_entry_id": item.allocation_entry_id,
        "allocation_id": round_row.allocation_id,
        "offer_id": offer.offer_id,
        "requested_quantity": item.requested_quantity,
        "allocated_quantity": item.allocated_quantity,
        "status": item.status,
        "priority_hash": item.priority_hash,
        "conditions_hash": commitment.conditions_hash,
        "seed_hash": round_row.seed_hash,
        "algorithm_version": round_row.algorithm_version,
        "self_verifiable": True,
        "shared_with_responder": False,
        "payment_created": False,
        "order_created": False,
        "created_at": item.created_at,
    }


@router.post("")
def allocate_collective_offer(payload: CollectiveAllocationCreate, db: Session = Depends(get_db)):
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.offer_id == payload.offer_id).one_or_none()
    if not offer:
        raise HTTPException(404, "collective offer not found")
    try:
        round_row = CollectiveAllocationService(db).allocate(offer, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CollectiveAllocationService(db).effective_public_allocation(offer)


@router.get("/offers/{offer_id}")
def get_effective_public_allocation(offer_id: str, db: Session = Depends(get_db)):
    offer = db.query(CollectiveMarketOffer).filter(CollectiveMarketOffer.offer_id == offer_id).one_or_none()
    if not offer:
        raise HTTPException(404, "collective offer not found")
    return CollectiveAllocationService(db).effective_public_allocation(offer)


@router.get("/users/{external_id}")
def list_user_private_allocations(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(CollectivePrivateAllocation)
        .filter(CollectivePrivateAllocation.user_id == user.id)
        .order_by(CollectivePrivateAllocation.created_at.desc())
        .all()
    )
    return {
        "allocations": [_private_out(item, db) for item in rows],
        "scope": "self_only",
        "shared_with_responders": False,
        "payment_created": False,
        "order_created": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
