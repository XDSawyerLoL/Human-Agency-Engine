from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..software_agent_models import SoftwareAgentRun
from ..software_agent_schemas import SoftwareAgentBootstrapRequest, SoftwareAgentLaunchRequest
from ..services.software_agent import SoftwareAgentSandboxService


router = APIRouter(prefix="/software-agent")


def _run_out(run: SoftwareAgentRun, *, final_response: str | None = None) -> dict:
    return {
        "run_id": run.run_id,
        "idempotency_key": run.idempotency_key,
        "repository": run.repository,
        "provider": run.provider,
        "workspace_path": run.workspace_path,
        "goal_hash": run.goal_hash,
        "goal_persisted": False,
        "quality_commands": run.quality_commands,
        "max_iterations": run.max_iterations,
        "worktree_required": run.worktree_required,
        "external_dispatch": run.external_dispatch,
        "conversation_id": run.conversation_id,
        "status": run.status,
        "execution_status": run.execution_status,
        "final_response_hash": run.final_response_hash,
        "final_response": final_response,
        "final_response_persisted": False,
        "failure_reason": run.failure_reason,
        "launched_at": run.launched_at,
        "last_checked_at": run.last_checked_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
    }


@router.get("/capabilities")
def capabilities():
    return SoftwareAgentSandboxService.capabilities()


@router.get("/readiness")
def readiness(db: Session = Depends(get_db)):
    return SoftwareAgentSandboxService(db).readiness()


@router.post("/bootstrap")
def bootstrap(payload: SoftwareAgentBootstrapRequest, db: Session = Depends(get_db)):
    try:
        manifest = SoftwareAgentSandboxService(db).bootstrap(payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "adapter_id": manifest.adapter_id,
        "version": manifest.version,
        "audience": manifest.audience,
        "supported_action_types": manifest.supported_action_types,
        "contract_hash": manifest.contract_hash,
        "external_dispatch_enabled": manifest.external_dispatch_enabled,
    }


@router.post("/runs")
def launch(payload: SoftwareAgentLaunchRequest, db: Session = Depends(get_db)):
    try:
        run = SoftwareAgentSandboxService(db).launch(payload)
    except ValueError as exc:
        status = 409 if "idempotency key" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _run_out(run)


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        run = SoftwareAgentSandboxService(db).get_run(run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _run_out(run)


@router.post("/runs/{run_id}/refresh")
def refresh(run_id: str, db: Session = Depends(get_db)):
    try:
        run, final_response = SoftwareAgentSandboxService(db).refresh(run_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 502
        raise HTTPException(status, str(exc)) from exc
    return _run_out(run, final_response=final_response)


@router.post("/runs/{run_id}/interrupt")
def interrupt(run_id: str, db: Session = Depends(get_db)):
    try:
        run = SoftwareAgentSandboxService(db).interrupt(run_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 502
        raise HTTPException(status, str(exc)) from exc
    return _run_out(run)


from .execution import router as execution_router  # noqa: E402

execution_router.include_router(router)
