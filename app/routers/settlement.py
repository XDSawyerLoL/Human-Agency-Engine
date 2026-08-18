from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..collective_offer_models import CollectiveMarketOffer
from ..db import get_db
from ..security import require_api_key
from ..services.settlement import CollectiveSettlementService
from ..settlement_schemas import CollectiveSettlementAssess

router = APIRouter(
    prefix="/collective-settlement",
    dependencies=[Depends(require_api_key)],
)


def _offer_or_404(db: Session, offer_id: str) -> CollectiveMarketOffer:
    offer = (
        db.query(CollectiveMarketOffer)
        .filter(CollectiveMarketOffer.offer_id == offer_id)
        .one_or_none()
    )
    if not offer:
        raise HTTPException(404, "collective offer not found")
    return offer


def _safe_public(offer: CollectiveMarketOffer, receipt) -> dict:
    body = CollectiveSettlementService.public_view(offer, receipt)
    if not body.get("published"):
        body.pop("receipt_id", None)
    return body


@router.post("/assess")
def assess_collective_settlement(
    payload: CollectiveSettlementAssess,
    db: Session = Depends(get_db),
):
    offer = _offer_or_404(db, payload.offer_id)
    try:
        receipt = CollectiveSettlementService(db).assess(offer)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _safe_public(offer, receipt)


@router.get("/offers/{offer_id}")
def get_current_collective_settlement_readiness(
    offer_id: str,
    db: Session = Depends(get_db),
):
    offer = _offer_or_404(db, offer_id)
    receipt = CollectiveSettlementService(db).effective_receipt(offer)
    return _safe_public(offer, receipt)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
