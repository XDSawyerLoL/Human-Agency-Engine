from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..delegation_models import AgentSigningIdentity, DelegationGrant, DelegationUse
from ..delegation_schemas import (
    DelegationConsume,
    DelegationIssue,
    DelegationRevoke,
    DelegationVerify,
    SigningIdentityRotate,
)
from ..models import User
from ..security import require_api_key
from ..services.delegation import DelegationService, _public_jwk

router = APIRouter(prefix="/v1/delegations")


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _grant_out(grant: DelegationGrant) -> dict:
    return {
        "grant_id": grant.grant_id,
        "candidate_id": grant.candidate_id,
        "audience": grant.audience,
        "capability": grant.capability,
        "mandate_version": grant.mandate_version,
        "action_type": grant.action_type,
        "action_fingerprint": grant.action_fingerprint,
        "constraints": grant.constraints,
        "max_uses": grant.max_uses,
        "use_count": grant.use_count,
        "issued_at": grant.issued_at,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
        "revocation_reason": grant.revocation_reason,
    }


@router.get("/keys/{key_id}")
def public_signing_key(key_id: str, db: Session = Depends(get_db)):
    identity = (
        db.query(AgentSigningIdentity)
        .filter(AgentSigningIdentity.key_id == key_id)
        .one_or_none()
    )
    if not identity:
        raise HTTPException(404, "signing key not found")
    return {
        "jwk": _public_jwk(identity),
        "created_at": identity.created_at,
        "revoked_at": identity.revoked_at,
    }


@router.post("/verify")
def verify_delegation(payload: DelegationVerify, db: Session = Depends(get_db)):
    try:
        verified = DelegationService(db).verify(payload.token, audience=payload.audience)
    except ValueError as exc:
        return {"valid": False, "reason": str(exc)}
    return {
        "valid": True,
        "header": verified["header"],
        "claims": verified["claims"],
        "public_jwk": verified["public_jwk"],
        "use_count": verified["grant"].use_count,
        "max_uses": verified["grant"].max_uses,
    }


@router.get(
    "/users/{external_id}/identity",
    dependencies=[Depends(require_api_key)],
)
def get_or_create_identity(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    try:
        identity = DelegationService(db).ensure_identity(user)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "key_id": identity.key_id,
        "algorithm": identity.algorithm,
        "jwk": _public_jwk(identity),
        "created_at": identity.created_at,
    }


@router.post(
    "/users/{external_id}/identity/rotate",
    dependencies=[Depends(require_api_key)],
)
def rotate_identity(
    external_id: str,
    payload: SigningIdentityRotate,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        identity = DelegationService(db).rotate_identity(user, payload.confirm)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "key_id": identity.key_id,
        "algorithm": identity.algorithm,
        "jwk": _public_jwk(identity),
        "created_at": identity.created_at,
    }


@router.post(
    "/users/{external_id}/grants",
    dependencies=[Depends(require_api_key)],
)
def issue_grant(
    external_id: str,
    payload: DelegationIssue,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        grant, bundle = DelegationService(db).issue(user, payload)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "grant": _grant_out(grant),
        "proof": bundle,
        "privacy": {
            "self_graph_included": False,
            "intents_included": False,
            "raw_personal_mandate_included": False,
        },
    }


@router.get(
    "/users/{external_id}/grants",
    dependencies=[Depends(require_api_key)],
)
def list_grants(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    grants = (
        db.query(DelegationGrant)
        .filter(DelegationGrant.user_id == user.id)
        .order_by(DelegationGrant.issued_at.desc())
        .all()
    )
    return [_grant_out(item) for item in grants]


@router.get(
    "/users/{external_id}/export",
    dependencies=[Depends(require_api_key)],
)
def export_delegation_audit(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    identities = (
        db.query(AgentSigningIdentity)
        .filter(AgentSigningIdentity.user_id == user.id)
        .order_by(AgentSigningIdentity.created_at.asc())
        .all()
    )
    grants = (
        db.query(DelegationGrant)
        .filter(DelegationGrant.user_id == user.id)
        .order_by(DelegationGrant.issued_at.asc())
        .all()
    )
    grant_ids = [item.id for item in grants]
    uses = (
        db.query(DelegationUse)
        .filter(DelegationUse.grant_id.in_(grant_ids))
        .order_by(DelegationUse.recorded_at.asc())
        .all()
        if grant_ids
        else []
    )
    grant_public_ids = {item.id: item.grant_id for item in grants}
    return {
        "identities": [
            {
                "key_id": item.key_id,
                "algorithm": item.algorithm,
                "public_jwk": _public_jwk(item),
                "created_at": item.created_at,
                "rotated_at": item.rotated_at,
                "revoked_at": item.revoked_at,
            }
            for item in identities
        ],
        "grants": [_grant_out(item) for item in grants],
        "uses": [
            {
                "grant_id": grant_public_ids.get(item.grant_id),
                "request_id": item.request_id,
                "audience": item.audience,
                "action_fingerprint": item.action_fingerprint,
                "metadata": item.metadata_json,
                "recorded_at": item.recorded_at,
            }
            for item in uses
        ],
        "private_keys_included": False,
        "bearer_tokens_included": False,
        "self_graph_included": False,
        "raw_intents_included": False,
        "raw_personal_mandate_included": False,
    }


@router.post(
    "/users/{external_id}/grants/{grant_id}/revoke",
    dependencies=[Depends(require_api_key)],
)
def revoke_grant(
    external_id: str,
    grant_id: str,
    payload: DelegationRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    grant = (
        db.query(DelegationGrant)
        .filter(DelegationGrant.grant_id == grant_id)
        .one_or_none()
    )
    if not grant:
        raise HTTPException(404, "delegation grant not found")
    try:
        grant = DelegationService(db).revoke(user, grant, payload.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _grant_out(grant)


@router.post("/consume", dependencies=[Depends(require_api_key)])
def consume_grant(payload: DelegationConsume, db: Session = Depends(get_db)):
    try:
        use = DelegationService(db).consume(payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    grant = db.query(DelegationGrant).filter(DelegationGrant.id == use.grant_id).one()
    return {
        "consumed": True,
        "grant_id": grant.grant_id,
        "request_id": use.request_id,
        "use_count": grant.use_count,
        "max_uses": grant.max_uses,
        "recorded_at": use.recorded_at,
    }


@router.get(
    "/users/{external_id}/uses",
    dependencies=[Depends(require_api_key)],
)
def list_uses(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    grants = db.query(DelegationGrant.id).filter(DelegationGrant.user_id == user.id).all()
    grant_ids = [row[0] for row in grants]
    if not grant_ids:
        return []
    uses = (
        db.query(DelegationUse)
        .filter(DelegationUse.grant_id.in_(grant_ids))
        .order_by(DelegationUse.recorded_at.desc())
        .all()
    )
    return [
        {
            "request_id": item.request_id,
            "audience": item.audience,
            "action_fingerprint": item.action_fingerprint,
            "metadata": item.metadata_json,
            "recorded_at": item.recorded_at,
        }
        for item in uses
    ]
