from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..execution_models import ExecutionDryRun, HumanCommitAuthorization, PolicyReceipt
from ..execution_schemas import (
    DualKeyDryRunRequest,
    HumanCommitConfirm,
    HumanCommitPrepare,
    HumanCommitRevoke,
)
from ..models import User
from ..security import require_api_key
from ..services.execution import DualKeyExecutionGateway, HumanCommitService

router = APIRouter(
    prefix="/v1/execution",
    dependencies=[Depends(require_api_key)],
)


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _commit_out(item: HumanCommitAuthorization) -> dict:
    return {
        "commit_id": item.commit_id,
        "candidate_id": item.candidate_id,
        "audience": item.audience,
        "mandate_version": item.mandate_version,
        "action_type": item.action_type,
        "action_fingerprint": item.action_fingerprint,
        "exact_action": item.exact_action,
        "rollback_plan": item.rollback_plan,
        "rollback_fingerprint": item.rollback_fingerprint,
        "status": item.status,
        "prepared_at": item.prepared_at,
        "confirmed_at": item.confirmed_at,
        "expires_at": item.expires_at,
        "consumed_at": item.consumed_at,
        "revoked_at": item.revoked_at,
        "bearer_token_included": False,
    }


def _dry_run_out(item: ExecutionDryRun) -> dict:
    return {
        "request_id": item.request_id,
        "candidate_id": item.candidate_id,
        "audience": item.audience,
        "action_fingerprint": item.action_fingerprint,
        "checks": item.checks,
        "status": item.status,
        "would_execute": item.would_execute,
        "external_dispatch": item.external_dispatch,
        "created_at": item.created_at,
    }


@router.post("/users/{external_id}/human-commits/prepare")
def prepare_human_commit(
    external_id: str,
    payload: HumanCommitPrepare,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        commit = HumanCommitService(db).prepare(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    receipt = db.query(PolicyReceipt).filter(PolicyReceipt.id == commit.policy_receipt_id).one()
    return {
        "commit": _commit_out(commit),
        "policy": {
            "engine_version": receipt.engine_version,
            "decision": receipt.decision,
            "receipt_hash": receipt.receipt_hash,
        },
        "second_confirmation": f"COMMIT {commit.commit_id} {commit.action_fingerprint[-12:]}",
    }


@router.post("/users/{external_id}/human-commits/{commit_id}/confirm")
def confirm_human_commit(
    external_id: str,
    commit_id: str,
    payload: HumanCommitConfirm,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        commit, token = HumanCommitService(db).confirm(user, commit_id, payload.confirm)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "commit": _commit_out(commit),
        "human_commit_token": token,
        "token_notice": "Returned once. Store only in the active execution flow; the server stores a SHA-256 hash.",
    }


@router.post("/users/{external_id}/human-commits/{commit_id}/revoke")
def revoke_human_commit(
    external_id: str,
    commit_id: str,
    payload: HumanCommitRevoke,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        commit = HumanCommitService(db).revoke(user, commit_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"commit": _commit_out(commit), "reason": payload.reason}


@router.get("/users/{external_id}/human-commits")
def list_human_commits(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    commits = (
        db.query(HumanCommitAuthorization)
        .filter(HumanCommitAuthorization.user_id == user.id)
        .order_by(HumanCommitAuthorization.prepared_at.desc())
        .all()
    )
    return [_commit_out(item) for item in commits]


@router.post("/dual-key/dry-run")
def dual_key_dry_run(payload: DualKeyDryRunRequest, db: Session = Depends(get_db)):
    try:
        dry_run = DualKeyExecutionGateway(db).dry_run(payload)
    except ValueError as exc:
        status = 409 if "already been used" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _dry_run_out(dry_run)


@router.get("/users/{external_id}/dry-runs")
def list_dry_runs(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    rows = (
        db.query(ExecutionDryRun)
        .filter(ExecutionDryRun.user_id == user.id)
        .order_by(ExecutionDryRun.created_at.desc())
        .all()
    )
    return [_dry_run_out(item) for item in rows]
