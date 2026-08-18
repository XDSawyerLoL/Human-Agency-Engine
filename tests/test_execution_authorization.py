import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.delegation_models import DelegationGrant
from app.execution_models import ExecutionDryRun, HumanCommitAuthorization, PolicyReceipt
from app.main import app
from app.models import User
from app.synthesis_models import CandidateIntervention

client = TestClient(app)


def _setup(uid: str, *, allow_execute: bool = True) -> int:
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    user = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2300,
            "monthly_fixed_costs": 1300,
            "liquid_cash": 1000,
            "minimum_cash_buffer": 200,
        },
    )
    assert user.status_code == 200
    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Increase agency while preserving exact human control.",
            "principles": ["reversible first", "explicit commitment"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": allow_execute},
            "notification_policy": {},
        },
    )
    assert mandate.status_code == 200

    db = SessionLocal()
    try:
        user_row = db.query(User).filter(User.external_id == uid).one()
        candidate = CandidateIntervention(
            user_id=user_row.id,
            candidate_key=uuid.uuid4().hex,
            source_type="test",
            source_ref="execution-authorization-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Exact reversible purchase-like action",
            rationale="Synthetic candidate used only to verify execution authorization boundaries.",
            intervention={
                "type": "reserve_reversible_offer",
                "reversible": True,
                "merchant": "merchant-agent.example",
                "amount": 42.0,
                "currency": "EUR",
                "lock_in_days": 0,
                "reversal_cost": 0,
            },
            effects={
                "option_value": {
                    "low": 0,
                    "central": 1,
                    "high": 1,
                    "unit": "option",
                    "direction": "higher_is_better",
                }
            },
            assumptions=[],
            evidence={"level": "personal_repeated", "sources": ["test"]},
            confidence=0.8,
            status="ready_for_review",
            decision_status="candidate_for_reversible_pilot",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate.id
    finally:
        db.close()


def _issue_execute(uid: str, candidate_id: int):
    return client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": "execute_reversible",
            "audience": "merchant-agent.example",
            "expires_in_seconds": 600,
            "max_uses": 1,
            "constraints": {
                "max_amount": 50,
                "currency": "EUR",
                "category": "synthetic",
                "purpose": "execute only the exact reversible candidate",
            },
            "confirm": f"ISSUE {candidate_id} execute_reversible",
            "execute_ack": True,
        },
    )


def _prepare_and_confirm(uid: str, candidate_id: int):
    prepared = client.post(
        f"/v1/execution/users/{uid}/human-commits/prepare",
        json={
            "candidate_id": candidate_id,
            "audience": "merchant-agent.example",
            "expires_in_seconds": 300,
            "rollback_plan": "Cancel the reservation and restore the pre-action state without external side effects.",
            "confirm": f"PREPARE COMMIT {candidate_id}",
        },
    )
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    commit_id = body["commit"]["commit_id"]
    assert body["policy"]["decision"] == "allow"
    assert body["policy"]["engine_version"] == "hae-policy-kernel-v1"

    confirmed = client.post(
        f"/v1/execution/users/{uid}/human-commits/{commit_id}/confirm",
        json={"confirm": body["second_confirmation"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["human_commit_token"], confirmed.json()["commit"]


def test_dual_key_dry_run_requires_both_authorities_and_never_dispatches():
    uid = "execution-dual-key-a"
    candidate_id = _setup(uid)
    issued = _issue_execute(uid, candidate_id)
    assert issued.status_code == 200, issued.text
    delegation_token = issued.json()["proof"]["token"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]

    human_token, commit = _prepare_and_confirm(uid, candidate_id)
    assert commit["action_fingerprint"] == fingerprint

    missing_human = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": "x" * 24,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": "dual-key-missing-human-0001",
        },
    )
    assert missing_human.status_code == 400

    dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": human_token,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": "dual-key-authorized-0001",
        },
    )
    assert dry_run.status_code == 200, dry_run.text
    body = dry_run.json()
    assert body["status"] == "authorized_dry_run"
    assert body["would_execute"] is False
    assert body["external_dispatch"] is False
    assert body["checks"]["external_dispatch_enabled"] is False
    assert body["checks"]["delegation_signature_valid"] is True
    assert body["checks"]["human_commit_valid"] is True

    verified = client.post(
        "/v1/delegations/verify",
        json={"token": delegation_token, "audience": "merchant-agent.example"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["use_count"] == 0

    db = SessionLocal()
    try:
        row = db.query(HumanCommitAuthorization).filter(HumanCommitAuthorization.commit_id == commit["commit_id"]).one()
        assert row.status == "confirmed"
        assert row.consumed_at is None
    finally:
        db.close()


def test_mandate_change_invalidates_both_authorities_before_dry_run():
    uid = "execution-mandate-b"
    candidate_id = _setup(uid)
    issued = _issue_execute(uid, candidate_id)
    assert issued.status_code == 200
    delegation_token = issued.json()["proof"]["token"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]
    human_token, _ = _prepare_and_confirm(uid, candidate_id)

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Changed mandate: no reversible execution for now.",
            "principles": ["manual only"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": human_token,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": "dual-key-stale-mandate-0001",
        },
    )
    assert dry_run.status_code == 400
    assert "mandate changed" in dry_run.text.lower()


def test_policy_denial_is_persisted_when_execution_is_not_allowed():
    uid = "execution-policy-deny-c"
    candidate_id = _setup(uid, allow_execute=False)
    prepared = client.post(
        f"/v1/execution/users/{uid}/human-commits/prepare",
        json={
            "candidate_id": candidate_id,
            "audience": "merchant-agent.example",
            "expires_in_seconds": 300,
            "rollback_plan": "Return to the exact prior state.",
            "confirm": f"PREPARE COMMIT {candidate_id}",
        },
    )
    assert prepared.status_code == 400
    assert "policy kernel denied" in prepared.text.lower()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        receipt = (
            db.query(PolicyReceipt)
            .filter(PolicyReceipt.user_id == user.id)
            .order_by(PolicyReceipt.created_at.desc())
            .first()
        )
        assert receipt is not None
        assert receipt.decision == "deny"
        assert "personal mandate does not allow reversible execution" in receipt.reasons
    finally:
        db.close()


def test_execution_export_never_contains_reusable_secret_and_delete_cascades():
    uid = "execution-sovereignty-d"
    candidate_id = _setup(uid)
    issued = _issue_execute(uid, candidate_id)
    assert issued.status_code == 200
    delegation_token = issued.json()["proof"]["token"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]
    human_token, _ = _prepare_and_confirm(uid, candidate_id)

    dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": human_token,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": "dual-key-sovereignty-0001",
        },
    )
    assert dry_run.status_code == 200

    exported = client.get(f"/v1/execution/users/{uid}/export")
    assert exported.status_code == 200
    body = exported.json()
    assert body["policy_receipts"]
    assert body["human_commits"]
    assert body["dry_runs"]
    assert body["human_commit_tokens_included"] is False
    assert body["delegation_tokens_included"] is False
    serialized = str(body)
    assert human_token not in serialized
    assert delegation_token not in serialized
    assert "token_hash" not in serialized

    db = SessionLocal()
    try:
        user_id = db.query(User).filter(User.external_id == uid).one().id
    finally:
        db.close()

    deleted = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": f"DELETE {uid}"},
    )
    assert deleted.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(PolicyReceipt).filter(PolicyReceipt.user_id == user_id).count() == 0
        assert db.query(HumanCommitAuthorization).filter(HumanCommitAuthorization.user_id == user_id).count() == 0
        assert db.query(ExecutionDryRun).filter(ExecutionDryRun.user_id == user_id).count() == 0
        assert db.query(DelegationGrant).filter(DelegationGrant.user_id == user_id).count() == 0
    finally:
        db.close()
