from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.vault import ALLOWED_CLAIMS, SelectiveDisclosureVaultService
from ..vault_models import SelectiveDisclosureGrant, UserVaultClaim
from ..vault_schemas import (
    DisclosureGrantConsume,
    DisclosureGrantIssue,
    DisclosureGrantRevoke,
    DisclosureGrantVerify,
    VaultClaimDelete,
    VaultClaimWrite,
)

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])
public_router = APIRouter(prefix="/vault")


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _claim_meta(item: UserVaultClaim) -> dict:
    return {
        "claim_type": item.claim_type,
        "value_fingerprint": item.value_fingerprint,
        "version": item.version,
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "raw_value_included": False,
        "encrypted_at_rest": True,
    }


def _grant_meta(item: SelectiveDisclosureGrant) -> dict:
    return {
        "grant_id": item.grant_id,
        "subject_ref": item.subject_ref,
        "audience": item.audience,
        "claim_types": item.claim_types,
        "claim_set_hash": item.claim_set_hash,
        "status": item.status,
        "use_count": item.use_count,
        "issued_at": item.issued_at,
        "expires_at": item.expires_at,
        "consumed_at": item.consumed_at,
        "revoked_at": item.revoked_at,
        "bearer_token_stored_in_database": False,
        "raw_values_included": False,
        "payment_claims_allowed": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.put("/users/{external_id}/claims/{claim_type}")
def store_vault_claim(
    external_id: str,
    claim_type: str,
    payload: VaultClaimWrite,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        row = SelectiveDisclosureVaultService(db).store_claim(
            user, claim_type, payload.value, payload.confirm
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _claim_meta(row)


@router.delete("/users/{external_id}/claims/{claim_type}")
def delete_vault_claim(
    external_id: str,
    claim_type: str,
    payload: VaultClaimDelete,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        SelectiveDisclosureVaultService(db).delete_claim(user, claim_type, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"deleted": True, "claim_type": claim_type}


@router.get("/users/{external_id}/claims")
def list_vault_claim_metadata(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(UserVaultClaim)
        .filter(UserVaultClaim.user_id == user.id)
        .order_by(UserVaultClaim.claim_type.asc())
        .all()
    )
    return {
        "claims": [_claim_meta(item) for item in rows],
        "allowed_claim_types": sorted(ALLOWED_CLAIMS),
        "raw_values_included": False,
        "payment_claims_allowed": False,
    }


@router.post("/users/{external_id}/disclosures")
def issue_selective_disclosure(
    external_id: str,
    payload: DisclosureGrantIssue,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        grant, proof = SelectiveDisclosureVaultService(db).issue(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "grant": _grant_meta(grant),
        "proof": proof,
        "one_time": True,
        "raw_values_in_proof": False,
        "payment_claims_allowed": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@public_router.post("/disclosures/verify")
def verify_selective_disclosure(
    payload: DisclosureGrantVerify,
    db: Session = Depends(get_db),
):
    try:
        return SelectiveDisclosureVaultService(db).verify(payload.token, payload.audience)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/disclosures/consume")
def consume_selective_disclosure(
    payload: DisclosureGrantConsume,
    db: Session = Depends(get_db),
):
    try:
        use, disclosed = SelectiveDisclosureVaultService(db).consume(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "consumed": True,
        "request_id": use.request_id,
        "audience": use.audience,
        "disclosed_claims": disclosed,
        "disclosed_claim_types": use.disclosed_claim_types,
        "payment_claims_allowed": False,
        "external_dispatch": False,
        "payment_created": False,
        "order_created": False,
    }


@router.post("/users/{external_id}/disclosures/{grant_id}/revoke")
def revoke_selective_disclosure(
    external_id: str,
    grant_id: str,
    payload: DisclosureGrantRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    grant = (
        db.query(SelectiveDisclosureGrant)
        .filter(SelectiveDisclosureGrant.grant_id == grant_id)
        .one_or_none()
    )
    if not grant:
        raise HTTPException(404, "disclosure grant not found")
    try:
        grant = SelectiveDisclosureVaultService(db).revoke(user, grant, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _grant_meta(grant)


@router.get("/users/{external_id}/disclosures")
def list_user_disclosures(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(SelectiveDisclosureGrant)
        .filter(SelectiveDisclosureGrant.user_id == user.id)
        .order_by(SelectiveDisclosureGrant.issued_at.desc())
        .all()
    )
    return {
        "grants": [_grant_meta(item) for item in rows],
        "scope": "self_only",
        "bearer_tokens_included": False,
        "raw_values_included": False,
        "payment_claims_allowed": False,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
agency_router.include_router(public_router)
