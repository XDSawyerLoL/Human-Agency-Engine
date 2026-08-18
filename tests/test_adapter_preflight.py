import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.adapter_models import AdapterPreflight
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User
from app.synthesis_models import CandidateIntervention

client = TestClient(app)


def _setup_authorized_dry_run(uid: str, request_id: str):
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    assert client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2400,
            "monthly_fixed_costs": 1300,
            "liquid_cash": 1100,
            "minimum_cash_buffer": 200,
        },
    ).status_code == 200
    assert client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Allow only exact reversible execution after explicit authorization.",
            "principles": ["idempotent", "rollback first"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": True},
            "notification_policy": {},
        },
    ).status_code == 200

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        candidate = CandidateIntervention(
            user_id=user.id,
            candidate_key=uuid.uuid4().hex,
            source_type="test",
            source_ref="adapter-preflight-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Reversible reservation",
            rationale="Synthetic action for adapter contract tests.",
            intervention={
                "type": "reserve_reversible_offer",
                "reversible": True,
                "amount": 42.0,
                "currency": "EUR",
                "reversal_cost": 0,
            },
            effects={},
            assumptions=[],
            evidence={"level": "personal_repeated", "sources": ["test"]},
            confidence=0.8,
            status="ready_for_review",
            decision_status="candidate_for_reversible_pilot",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        candidate_id = candidate.id
    finally:
        db.close()

    issued = client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": "execute_reversible",
            "audience": "merchant-agent.example",
            "expires_in_seconds": 600,
            "max_uses": 1,
            "constraints": {"max_amount": 50, "currency": "EUR"},
            "confirm": f"ISSUE {candidate_id} execute_reversible",
            "execute_ack": True,
        },
    )
    assert issued.status_code == 200, issued.text
    delegation_token = issued.json()["proof"]["token"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]

    prepared = client.post(
        f"/v1/execution/users/{uid}/human-commits/prepare",
        json={
            "candidate_id": candidate_id,
            "audience": "merchant-agent.example",
            "expires_in_seconds": 300,
            "rollback_plan": "Cancel the reservation and restore the exact pre-action state.",
            "confirm": f"PREPARE COMMIT {candidate_id}",
        },
    )
    assert prepared.status_code == 200, prepared.text
    commit_id = prepared.json()["commit"]["commit_id"]
    confirmed = client.post(
        f"/v1/execution/users/{uid}/human-commits/{commit_id}/confirm",
        json={"confirm": prepared.json()["second_confirmation"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    human_token = confirmed.json()["human_commit_token"]

    dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": human_token,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": request_id,
        },
    )
    assert dry_run.status_code == 200, dry_run.text
    assert dry_run.json()["external_dispatch"] is False
    return candidate_id, delegation_token, human_token, fingerprint


def _register(adapter_id: str, version: str = "1.0.0", **overrides):
    payload = {
        "adapter_id": adapter_id,
        "version": version,
        "audience": "merchant-agent.example",
        "supported_action_types": ["reserve_reversible_offer"],
        "reversible_only": True,
        "supports_idempotency": True,
        "supports_rollback": True,
        "side_effect_free_preflight": True,
        "external_dispatch_enabled": False,
        "confirm": f"REGISTER ADAPTER {adapter_id} {version}",
    }
    payload.update(overrides)
    return client.post("/v1/execution/adapters", json=payload)


def test_registry_rejects_unsafe_contracts_and_versions_are_immutable():
    unsafe = _register("unsafe-dispatch-adapter", external_dispatch_enabled=True)
    assert unsafe.status_code == 400
    assert "external dispatch" in unsafe.text.lower()

    safe = _register("immutable-safe-adapter")
    assert safe.status_code == 200, safe.text
    assert safe.json()["external_dispatch_enabled"] is False
    assert safe.json()["contract_hash"].startswith("sha256:")

    changed = _register(
        "immutable-safe-adapter",
        supported_action_types=["reserve_reversible_offer", "another_action"],
    )
    assert changed.status_code == 400
    assert "immutable" in changed.text.lower()


def test_adapter_preflight_is_local_idempotent_and_side_effect_free():
    uid = "adapter-preflight-a"
    dry_run_request_id = "adapter-authorized-dry-run-0001"
    _, delegation_token, human_token, fingerprint = _setup_authorized_dry_run(uid, dry_run_request_id)

    registered = _register("local-preflight-adapter")
    assert registered.status_code == 200, registered.text

    payload = {
        "dry_run_request_id": dry_run_request_id,
        "adapter_id": "local-preflight-adapter",
        "version": "1.0.0",
        "idempotency_key": "preflight-idempotency-0001",
    }
    first = client.post("/v1/execution/adapters/preflight", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "contract_compatible"
    assert body["action_fingerprint"] == fingerprint
    assert body["external_probe_performed"] is False
    assert body["external_dispatch"] is False
    assert body["checks"]["side_effect_free_preflight"] is True
    assert body["checks"]["current_policy_decision"] == "allow"

    repeated = client.post("/v1/execution/adapters/preflight", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["preflight_id"] == body["preflight_id"]

    second_dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": human_token,
            "audience": "merchant-agent.example",
            "action_fingerprint": fingerprint,
            "request_id": "adapter-authorized-dry-run-0002",
        },
    )
    assert second_dry_run.status_code == 200
    collision = client.post(
        "/v1/execution/adapters/preflight",
        json={**payload, "dry_run_request_id": "adapter-authorized-dry-run-0002"},
    )
    assert collision.status_code == 409


def test_preflight_rejects_adapter_with_wrong_audience_or_action_type():
    uid = "adapter-preflight-b"
    dry_run_request_id = "adapter-wrong-contract-dry-run-0001"
    _setup_authorized_dry_run(uid, dry_run_request_id)

    wrong_audience = _register("wrong-audience-adapter", audience="other-agent.example")
    assert wrong_audience.status_code == 200
    response = client.post(
        "/v1/execution/adapters/preflight",
        json={
            "dry_run_request_id": dry_run_request_id,
            "adapter_id": "wrong-audience-adapter",
            "version": "1.0.0",
            "idempotency_key": "wrong-audience-key-0001",
        },
    )
    assert response.status_code == 400
    assert "audience" in response.text.lower()

    wrong_action = _register("wrong-action-adapter", supported_action_types=["different_action"])
    assert wrong_action.status_code == 200
    response = client.post(
        "/v1/execution/adapters/preflight",
        json={
            "dry_run_request_id": dry_run_request_id,
            "adapter_id": "wrong-action-adapter",
            "version": "1.0.0",
            "idempotency_key": "wrong-action-key-0001",
        },
    )
    assert response.status_code == 400
    assert "does not support" in response.text.lower()


def test_user_delete_removes_preflights_but_not_platform_adapter_manifest():
    uid = "adapter-preflight-sovereignty-c"
    dry_run_request_id = "adapter-delete-dry-run-0001"
    _setup_authorized_dry_run(uid, dry_run_request_id)
    assert _register("platform-adapter-survives-user-delete").status_code == 200
    created = client.post(
        "/v1/execution/adapters/preflight",
        json={
            "dry_run_request_id": dry_run_request_id,
            "adapter_id": "platform-adapter-survives-user-delete",
            "version": "1.0.0",
            "idempotency_key": "delete-preflight-key-0001",
        },
    )
    assert created.status_code == 200, created.text

    db = SessionLocal()
    try:
        user_id = db.query(User).filter(User.external_id == uid).one().id
        assert db.query(AdapterPreflight).filter(AdapterPreflight.user_id == user_id).count() == 1
    finally:
        db.close()

    deleted = client.delete(f"/v1/users/{uid}", params={"confirm": f"DELETE {uid}"})
    assert deleted.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(AdapterPreflight).filter(AdapterPreflight.user_id == user_id).count() == 0
    finally:
        db.close()

    manifests = client.get("/v1/execution/adapters")
    assert manifests.status_code == 200
    assert any(item["adapter_id"] == "platform-adapter-survives-user-delete" for item in manifests.json())
