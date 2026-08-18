from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..readiness_models import ExecutionReadinessReceipt
from ..readiness_schemas import ExecutionReadinessAssess
from ..security import require_api_key
from ..services.readiness import ExecutionReadinessService

router = APIRouter(
    prefix="/readiness",
    dependencies=[Depends(require_api_key)],
)


def _receipt_out(item: ExecutionReadinessReceipt) -> dict:
    return {
        "receipt_id": item.receipt_id,
        "candidate_id": item.candidate_id,
        "preflight_id": item.preflight_id,
        "attestation_id": item.attestation_id,
        "mandate_version": item.mandate_version,
        "action_fingerprint": item.action_fingerprint,
        "adapter_contract_hash": item.adapter_contract_hash,
        "attestation_evidence_hash": item.attestation_evidence_hash,
        "decision": item.decision,
        "reasons": item.reasons,
        "checks": item.checks,
        "external_dispatch_enabled": item.external_dispatch_enabled,
        "created_at": item.created_at,
    }


@router.post("")
def assess_readiness(payload: ExecutionReadinessAssess, db: Session = Depends(get_db)):
    try:
        receipt = ExecutionReadinessService(db).assess(payload.preflight_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _receipt_out(receipt)


@router.get("/users/{external_id}")
def list_user_readiness(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    rows = (
        db.query(ExecutionReadinessReceipt)
        .filter(ExecutionReadinessReceipt.user_id == user.id)
        .order_by(ExecutionReadinessReceipt.created_at.desc())
        .all()
    )
    return {
        "receipts": [_receipt_out(item) for item in rows],
        "external_dispatch_enabled": False,
        "reusable_authorization_secrets_included": False,
    }


from .adapters import router as adapters_router  # noqa: E402

adapters_router.include_router(router)
