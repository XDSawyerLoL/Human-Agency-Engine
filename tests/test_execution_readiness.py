from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.readiness_models import ExecutionReadinessReceipt
from tests.test_adapter_preflight import _register, _setup_authorized_dry_run
from tests.test_sandbox_attestation import _evidence, _runner, _signed_submission

client = TestClient(app)


def _preflight(uid: str, adapter_id: str, dry_run_request_id: str, idempotency_key: str):
    _setup_authorized_dry_run(uid, dry_run_request_id)
    registered = _register(adapter_id)
    assert registered.status_code == 200, registered.text
    response = client.post(
        "/v1/execution/adapters/preflight",
        json={
            "dry_run_request_id": dry_run_request_id,
            "adapter_id": adapter_id,
            "version": "1.0.0",
            "idempotency_key": idempotency_key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["preflight_id"]


def _attest(adapter_id: str, runner_id: str, run_id: str):
    private, _ = _runner(runner_id)
    evidence = _evidence(run_id)
    response = client.post(
        "/v1/execution/adapters/sandbox/attestations",
        json=_signed_submission(adapter_id, runner_id, private, evidence),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "passed"
    return response.json()


def test_readiness_requires_full_chain_and_still_never_enables_dispatch():
    uid = "readiness-full-chain-a"
    adapter_id = "readiness-full-chain-adapter"
    preflight_id = _preflight(
        uid,
        adapter_id,
        "readiness-dry-run-0001",
        "readiness-preflight-key-0001",
    )
    attestation = _attest(adapter_id, "readiness-runner-a", "readiness-sandbox-run-0001")

    response = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "ready_for_controlled_integration"
    assert body["reasons"] == []
    assert body["external_dispatch_enabled"] is False
    assert body["checks"]["dual_key_dry_run_authorized"] is True
    assert body["checks"]["adapter_preflight_compatible"] is True
    assert body["checks"]["sandbox_attestation_effective"] is True
    assert body["checks"]["current_policy_allow"] is True
    assert body["attestation_evidence_hash"] == attestation["evidence_hash"]


def test_missing_or_revoked_sandbox_attestation_blocks_current_readiness():
    uid = "readiness-attestation-b"
    adapter_id = "readiness-attestation-adapter"
    preflight_id = _preflight(
        uid,
        adapter_id,
        "readiness-attestation-dry-run-0001",
        "readiness-attestation-key-0001",
    )

    before = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert before.status_code == 200
    assert before.json()["decision"] == "blocked"
    assert any("sandbox attestation" in reason.lower() for reason in before.json()["reasons"])

    runner_id = "readiness-runner-b"
    _attest(adapter_id, runner_id, "readiness-sandbox-run-0002")
    active = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert active.status_code == 200
    assert active.json()["decision"] == "ready_for_controlled_integration"

    revoked = client.post(
        f"/v1/execution/adapters/sandbox/runners/{runner_id}/revoke",
        json={"confirm": f"REVOKE SANDBOX RUNNER {runner_id}"},
    )
    assert revoked.status_code == 200

    after = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert after.status_code == 200
    assert after.json()["decision"] == "blocked"
    assert after.json()["checks"]["sandbox_attestation_effective"] is False


def test_personal_mandate_change_blocks_readiness_even_with_valid_sandbox_evidence():
    uid = "readiness-mandate-c"
    adapter_id = "readiness-mandate-adapter"
    preflight_id = _preflight(
        uid,
        adapter_id,
        "readiness-mandate-dry-run-0001",
        "readiness-mandate-key-0001",
    )
    _attest(adapter_id, "readiness-runner-c", "readiness-sandbox-run-0003")

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Manual control only after policy change.",
            "principles": ["manual only"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    response = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "blocked"
    reasons = " ".join(response.json()["reasons"]).lower()
    assert "personal mandate changed" in reasons
    assert response.json()["checks"]["current_policy_allow"] is False
    assert response.json()["external_dispatch_enabled"] is False


def test_readiness_receipts_are_user_owned_and_delete_with_user():
    uid = "readiness-delete-d"
    adapter_id = "readiness-delete-adapter"
    preflight_id = _preflight(
        uid,
        adapter_id,
        "readiness-delete-dry-run-0001",
        "readiness-delete-key-0001",
    )
    _attest(adapter_id, "readiness-runner-d", "readiness-sandbox-run-0004")
    created = client.post(
        "/v1/execution/adapters/readiness",
        json={"preflight_id": preflight_id},
    )
    assert created.status_code == 200

    db = SessionLocal()
    try:
        user_id = db.query(User).filter(User.external_id == uid).one().id
        assert db.query(ExecutionReadinessReceipt).filter(ExecutionReadinessReceipt.user_id == user_id).count() == 1
    finally:
        db.close()

    deleted = client.delete(f"/v1/users/{uid}", params={"confirm": f"DELETE {uid}"})
    assert deleted.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(ExecutionReadinessReceipt).filter(ExecutionReadinessReceipt.user_id == user_id).count() == 0
    finally:
        db.close()
