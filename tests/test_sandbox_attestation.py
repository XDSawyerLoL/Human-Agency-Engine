import base64
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.adapter_models import ExecutionAdapterManifest
from app.db import SessionLocal, engine
from app.main import app
from app.services.policy import canonical_json
from app.services.sandbox import sandbox_signed_payload

client = TestClient(app)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _register_adapter(adapter_id: str):
    response = client.post(
        "/v1/execution/adapters",
        json={
            "adapter_id": adapter_id,
            "version": "1.0.0",
            "audience": "merchant-agent.example",
            "supported_action_types": ["reserve_reversible_offer"],
            "reversible_only": True,
            "supports_idempotency": True,
            "supports_rollback": True,
            "side_effect_free_preflight": True,
            "external_dispatch_enabled": False,
            "confirm": f"REGISTER ADAPTER {adapter_id} 1.0.0",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _runner(runner_id: str):
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    response = client.post(
        "/v1/execution/adapters/sandbox/runners",
        json={
            "runner_id": runner_id,
            "label": "CI sandbox runner",
            "public_key_b64": _b64u(public_raw),
            "confirm": f"TRUST SANDBOX RUNNER {runner_id}",
        },
    )
    assert response.status_code == 200, response.text
    return private, response.json()


def _evidence(run_id: str, *, rollback_ok: bool = True):
    initial = {"reservations": [], "balance_delta": 0}
    held = {"reservations": ["r1"], "balance_delta": 0}
    partial = {"reservations": ["r1"], "balance_delta": 0, "partial_attempts": 0}
    return {
        "run_id": run_id,
        "observed_at_epoch": int(time.time()),
        "initial_state": initial,
        "state_after_preflight": initial,
        "first_result": {"reservation_id": "r1", "status": "held"},
        "state_after_first": held,
        "repeat_result": {"reservation_id": "r1", "status": "held"},
        "state_after_repeat": held,
        "partial_failure_state_before": partial,
        "partial_failure_state_after": partial,
        "state_after_rollback": initial if rollback_ok else held,
    }


def _signed_submission(adapter_id: str, runner_id: str, private, evidence: dict):
    db = SessionLocal()
    try:
        manifest = (
            db.query(ExecutionAdapterManifest)
            .filter(
                ExecutionAdapterManifest.adapter_id == adapter_id,
                ExecutionAdapterManifest.version == "1.0.0",
            )
            .one()
        )
        payload = sandbox_signed_payload(manifest, "hae-adapter-sandbox-v1", evidence)
    finally:
        db.close()
    signature = private.sign(canonical_json(payload))
    return {
        "adapter_id": adapter_id,
        "version": "1.0.0",
        "runner_id": runner_id,
        "suite_version": "hae-adapter-sandbox-v1",
        "valid_for_seconds": 604800,
        "evidence": evidence,
        "signature_b64": _b64u(signature),
    }


def test_signed_passing_evidence_becomes_effective_without_storing_raw_snapshots():
    adapter_id = "sandbox-pass-adapter"
    runner_id = "sandbox-runner-pass"
    _register_adapter(adapter_id)
    private, _ = _runner(runner_id)
    evidence = _evidence("sandbox-pass-run-0001")
    submission = _signed_submission(adapter_id, runner_id, private, evidence)

    attested = client.post("/v1/execution/adapters/sandbox/attestations", json=submission)
    assert attested.status_code == 200, attested.text
    body = attested.json()
    assert body["status"] == "passed"
    assert body["checks"] == {
        "preflight_no_side_effect": True,
        "idempotency_verified": True,
        "partial_failure_safe": True,
        "rollback_restored": True,
    }
    assert body["raw_evidence_included"] is False
    assert body["external_dispatch_enabled"] is False

    effective = client.get(f"/v1/execution/adapters/sandbox/effective/{adapter_id}/1.0.0")
    assert effective.status_code == 200
    assert effective.json()["sandbox_attested"] is True
    assert effective.json()["external_dispatch_enabled"] is False

    columns = {column["name"] for column in inspect(engine).get_columns("adapter_sandbox_attestations")}
    assert "initial_state" not in columns
    assert "state_after_rollback" not in columns
    assert "evidence_hash" in columns
    assert "rollback_state_hash" in columns


def test_invalid_signature_is_rejected_even_when_evidence_would_pass():
    adapter_id = "sandbox-signature-adapter"
    runner_id = "sandbox-runner-signature"
    _register_adapter(adapter_id)
    trusted_private, _ = _runner(runner_id)
    attacker_private = Ed25519PrivateKey.generate()
    evidence = _evidence("sandbox-invalid-signature-0001")
    submission = _signed_submission(adapter_id, runner_id, trusted_private, evidence)

    db = SessionLocal()
    try:
        manifest = db.query(ExecutionAdapterManifest).filter(ExecutionAdapterManifest.adapter_id == adapter_id).one()
        payload = sandbox_signed_payload(manifest, "hae-adapter-sandbox-v1", evidence)
    finally:
        db.close()
    submission["signature_b64"] = _b64u(attacker_private.sign(canonical_json(payload)))

    response = client.post("/v1/execution/adapters/sandbox/attestations", json=submission)
    assert response.status_code == 400
    assert "signature" in response.text.lower()


def test_failed_rollback_is_recorded_as_failed_and_never_effective():
    adapter_id = "sandbox-failed-rollback-adapter"
    runner_id = "sandbox-runner-failed-rollback"
    _register_adapter(adapter_id)
    private, _ = _runner(runner_id)
    evidence = _evidence("sandbox-failed-rollback-0001", rollback_ok=False)
    submission = _signed_submission(adapter_id, runner_id, private, evidence)

    response = client.post("/v1/execution/adapters/sandbox/attestations", json=submission)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["checks"]["rollback_restored"] is False

    effective = client.get(f"/v1/execution/adapters/sandbox/effective/{adapter_id}/1.0.0")
    assert effective.status_code == 200
    assert effective.json()["sandbox_attested"] is False


def test_runner_run_id_replay_with_different_signed_evidence_is_rejected():
    adapter_id = "sandbox-replay-adapter"
    runner_id = "sandbox-runner-replay"
    _register_adapter(adapter_id)
    private, _ = _runner(runner_id)
    first_evidence = _evidence("sandbox-replay-run-0001")
    first = client.post(
        "/v1/execution/adapters/sandbox/attestations",
        json=_signed_submission(adapter_id, runner_id, private, first_evidence),
    )
    assert first.status_code == 200

    changed_evidence = _evidence("sandbox-replay-run-0001", rollback_ok=False)
    replay = client.post(
        "/v1/execution/adapters/sandbox/attestations",
        json=_signed_submission(adapter_id, runner_id, private, changed_evidence),
    )
    assert replay.status_code == 409
    assert "replayed" in replay.text.lower()


def test_revoking_trusted_runner_invalidates_previously_effective_attestation():
    adapter_id = "sandbox-revocation-adapter"
    runner_id = "sandbox-runner-revocation"
    _register_adapter(adapter_id)
    private, _ = _runner(runner_id)
    evidence = _evidence("sandbox-revocation-run-0001")
    response = client.post(
        "/v1/execution/adapters/sandbox/attestations",
        json=_signed_submission(adapter_id, runner_id, private, evidence),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "passed"

    before = client.get(f"/v1/execution/adapters/sandbox/effective/{adapter_id}/1.0.0")
    assert before.json()["sandbox_attested"] is True

    revoked = client.post(
        f"/v1/execution/adapters/sandbox/runners/{runner_id}/revoke",
        json={"confirm": f"REVOKE SANDBOX RUNNER {runner_id}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    after = client.get(f"/v1/execution/adapters/sandbox/effective/{adapter_id}/1.0.0")
    assert after.status_code == 200
    assert after.json()["sandbox_attested"] is False
