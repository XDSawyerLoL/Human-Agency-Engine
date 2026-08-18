from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..adapter_models import ExecutionAdapterManifest
from ..db import get_db
from ..sandbox_models import AdapterSandboxAttestation, SandboxRunnerIdentity
from ..sandbox_schemas import SandboxAttestationSubmit, SandboxRunnerRegister, SandboxRunnerRevoke
from ..security import require_api_key
from ..services.sandbox import SandboxAttestationService, SandboxRunnerRegistry

router = APIRouter(
    prefix="/sandbox",
    dependencies=[Depends(require_api_key)],
)


def _runner_out(item: SandboxRunnerIdentity) -> dict:
    return {
        "runner_id": item.runner_id,
        "label": item.label,
        "public_key_b64": item.public_key_b64,
        "key_fingerprint": item.key_fingerprint,
        "status": item.status,
        "created_at": item.created_at,
        "revoked_at": item.revoked_at,
    }


def _attestation_out(item: AdapterSandboxAttestation) -> dict:
    return {
        "attestation_id": item.attestation_id,
        "runner_run_id": item.runner_run_id,
        "suite_version": item.suite_version,
        "adapter_contract_hash": item.adapter_contract_hash,
        "evidence_hash": item.evidence_hash,
        "checks": {
            "preflight_no_side_effect": item.preflight_no_side_effect,
            "idempotency_verified": item.idempotency_verified,
            "partial_failure_safe": item.partial_failure_safe,
            "rollback_restored": item.rollback_restored,
        },
        "status": item.status,
        "observed_at": item.observed_at,
        "valid_until": item.valid_until,
        "created_at": item.created_at,
        "raw_evidence_included": False,
        "external_dispatch_enabled": False,
    }


@router.post("/runners")
def register_runner(payload: SandboxRunnerRegister, db: Session = Depends(get_db)):
    try:
        runner = SandboxRunnerRegistry(db).register(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _runner_out(runner)


@router.get("/runners")
def list_runners(db: Session = Depends(get_db)):
    rows = db.query(SandboxRunnerIdentity).order_by(SandboxRunnerIdentity.created_at.asc()).all()
    return [_runner_out(item) for item in rows]


@router.post("/runners/{runner_id}/revoke")
def revoke_runner(
    runner_id: str,
    payload: SandboxRunnerRevoke,
    db: Session = Depends(get_db),
):
    runner = (
        db.query(SandboxRunnerIdentity)
        .filter(SandboxRunnerIdentity.runner_id == runner_id)
        .one_or_none()
    )
    if not runner:
        raise HTTPException(404, "sandbox runner not found")
    try:
        runner = SandboxRunnerRegistry(db).revoke(runner, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _runner_out(runner)


@router.post("/attestations")
def submit_attestation(payload: SandboxAttestationSubmit, db: Session = Depends(get_db)):
    try:
        attestation = SandboxAttestationService(db).submit(payload)
    except ValueError as exc:
        status = 409 if "replayed" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _attestation_out(attestation)


@router.get("/attestations")
def list_attestations(
    adapter_id: str | None = Query(default=None),
    version: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(AdapterSandboxAttestation)
    if adapter_id is not None or version is not None:
        manifests = db.query(ExecutionAdapterManifest)
        if adapter_id is not None:
            manifests = manifests.filter(ExecutionAdapterManifest.adapter_id == adapter_id)
        if version is not None:
            manifests = manifests.filter(ExecutionAdapterManifest.version == version)
        ids = [item.id for item in manifests.all()]
        if not ids:
            return []
        query = query.filter(AdapterSandboxAttestation.adapter_manifest_id.in_(ids))
    rows = query.order_by(AdapterSandboxAttestation.created_at.desc()).all()
    return [_attestation_out(item) for item in rows]


@router.get("/effective/{adapter_id}/{version}")
def effective_attestation(adapter_id: str, version: str, db: Session = Depends(get_db)):
    manifest = (
        db.query(ExecutionAdapterManifest)
        .filter(
            ExecutionAdapterManifest.adapter_id == adapter_id,
            ExecutionAdapterManifest.version == version,
        )
        .one_or_none()
    )
    if not manifest:
        raise HTTPException(404, "adapter manifest not found")
    attestation = SandboxAttestationService(db).effective_for_manifest(manifest)
    return {
        "adapter_id": adapter_id,
        "version": version,
        "sandbox_attested": attestation is not None,
        "attestation": None if attestation is None else _attestation_out(attestation),
        "external_dispatch_enabled": False,
    }


from .adapters import router as adapters_router  # noqa: E402

adapters_router.include_router(router)
