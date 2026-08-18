from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..adapter_models import AdapterPreflight, ExecutionAdapterManifest
from ..adapter_schemas import AdapterManifestRegister, AdapterPreflightRequest
from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.adapters import AdapterPreflightService, AdapterRegistry

router = APIRouter(
    prefix="/adapters",
    dependencies=[Depends(require_api_key)],
)


def _manifest_out(item: ExecutionAdapterManifest) -> dict:
    return {
        "adapter_id": item.adapter_id,
        "version": item.version,
        "audience": item.audience,
        "supported_action_types": item.supported_action_types,
        "reversible_only": item.reversible_only,
        "supports_idempotency": item.supports_idempotency,
        "supports_rollback": item.supports_rollback,
        "side_effect_free_preflight": item.side_effect_free_preflight,
        "external_dispatch_enabled": item.external_dispatch_enabled,
        "status": item.status,
        "contract_hash": item.contract_hash,
        "created_at": item.created_at,
    }


def _preflight_out(item: AdapterPreflight) -> dict:
    return {
        "preflight_id": item.preflight_id,
        "dry_run_id": item.dry_run_id,
        "adapter_manifest_id": item.adapter_manifest_id,
        "idempotency_key": item.idempotency_key,
        "audience": item.audience,
        "action_type": item.action_type,
        "action_fingerprint": item.action_fingerprint,
        "adapter_contract_hash": item.adapter_contract_hash,
        "rollback_fingerprint": item.rollback_fingerprint,
        "checks": item.checks,
        "status": item.status,
        "external_probe_performed": item.external_probe_performed,
        "external_dispatch": item.external_dispatch,
        "created_at": item.created_at,
    }


@router.post("")
def register_adapter(payload: AdapterManifestRegister, db: Session = Depends(get_db)):
    try:
        manifest = AdapterRegistry(db).register(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _manifest_out(manifest)


@router.get("")
def list_adapters(db: Session = Depends(get_db)):
    rows = (
        db.query(ExecutionAdapterManifest)
        .order_by(ExecutionAdapterManifest.adapter_id.asc(), ExecutionAdapterManifest.created_at.desc())
        .all()
    )
    return [_manifest_out(item) for item in rows]


@router.post("/preflight")
def run_adapter_preflight(payload: AdapterPreflightRequest, db: Session = Depends(get_db)):
    try:
        preflight = AdapterPreflightService(db).run(payload)
    except ValueError as exc:
        status = 409 if "idempotency key" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _preflight_out(preflight)


@router.get("/users/{external_id}/preflights")
def list_user_preflights(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    rows = (
        db.query(AdapterPreflight)
        .filter(AdapterPreflight.user_id == user.id)
        .order_by(AdapterPreflight.created_at.desc())
        .all()
    )
    return {
        "preflights": [_preflight_out(item) for item in rows],
        "external_probe_data_included": False,
        "external_dispatch_records_included": False,
    }


from .execution import router as execution_router  # noqa: E402

execution_router.include_router(router)
