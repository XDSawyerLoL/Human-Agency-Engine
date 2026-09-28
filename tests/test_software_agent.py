import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import User
from app.software_agent_models import SoftwareAgentRun
from app.services.software_agent import SoftwareAgentSandboxService, _resolved_agent_profile_id
from app.synthesis_models import CandidateIntervention


client = TestClient(app)


def _authorized_preflight(uid: str, dry_run_request_id: str) -> str:
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
            "mission": "Allow exact reversible sandboxed software work after explicit authorization.",
            "principles": ["sandbox first", "rollback first", "no production dispatch"],
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
            source_ref="software-agent-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Sandboxed software patch",
            rationale="Exercise the AURA software-engine authorization path.",
            intervention={
                "type": "software_patch",
                "reversible": True,
                "repository": "XDSawyerLoL/Human-Agency-Engine",
                "reversal_cost": 0,
            },
            effects={},
            assumptions=[],
            evidence={"level": "personal_repeated", "sources": ["test"]},
            confidence=0.9,
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
            "audience": "aura-software-sandbox",
            "expires_in_seconds": 600,
            "max_uses": 1,
            "constraints": {},
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
            "audience": "aura-software-sandbox",
            "expires_in_seconds": 300,
            "rollback_plan": "Discard the dedicated worktree and return to the untouched base revision.",
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

    dry_run = client.post(
        "/v1/execution/dual-key/dry-run",
        json={
            "delegation_token": delegation_token,
            "human_commit_token": confirmed.json()["human_commit_token"],
            "audience": "aura-software-sandbox",
            "action_fingerprint": fingerprint,
            "request_id": dry_run_request_id,
        },
    )
    assert dry_run.status_code == 200, dry_run.text

    bootstrapped = client.post(
        "/v1/execution/software-agent/bootstrap",
        json={"confirm": "REGISTER AURA SOFTWARE ENGINE"},
    )
    assert bootstrapped.status_code == 200, bootstrapped.text

    preflight = client.post(
        "/v1/execution/adapters/preflight",
        json={
            "dry_run_request_id": dry_run_request_id,
            "adapter_id": "aura-software-engine",
            "version": "1.0.0",
            "idempotency_key": f"software-preflight-{uuid.uuid4().hex}",
        },
    )
    assert preflight.status_code == 200, preflight.text
    return preflight.json()["preflight_id"]


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "software_agent_enabled", True)
    monkeypatch.setattr(settings, "software_agent_base_url", "http://127.0.0.1:3000")
    monkeypatch.setattr(settings, "software_agent_session_api_key", "test-session-key")
    monkeypatch.setattr(settings, "software_agent_agent_profile_id", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "software_agent_agent_profile_id_file", "")
    monkeypatch.setattr(settings, "software_agent_workspace_root", "/workspace/repos")
    monkeypatch.setattr(
        settings,
        "software_agent_allowed_repositories",
        "XDSawyerLoL/Human-Agency-Engine",
    )
    monkeypatch.setattr(settings, "software_agent_max_iterations", 80)
    monkeypatch.setattr(settings, "software_agent_require_attestation", False)


def test_launch_uses_worktree_is_idempotent_and_does_not_persist_raw_goal(monkeypatch):
    _configure(monkeypatch)
    preflight_id = _authorized_preflight(
        "software-agent-launch-a",
        "software-agent-dry-run-launch-0001",
    )
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and path == "/server_info":
            return {"conversation_runtime": "docker"}
        assert method == "POST"
        assert path == "/api/conversations"
        return {
            "id": "11111111-1111-4111-8111-111111111111",
            "execution_status": "running",
        }

    monkeypatch.setattr(SoftwareAgentSandboxService, "_request", fake_request)

    goal = "Fix a deterministic regression in the test fixture without touching unrelated behavior."
    payload = {
        "preflight_id": preflight_id,
        "idempotency_key": "software-agent-idempotency-launch-0001",
        "repository": "XDSawyerLoL/Human-Agency-Engine",
        "goal": goal,
        "quality_commands": ["pytest -q tests/test_software_agent.py"],
        "max_iterations": 25,
    }
    first = client.post("/v1/execution/software-agent/runs", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "running"
    assert body["worktree_required"] is True
    assert body["external_dispatch"] is False
    assert body["goal_persisted"] is False
    assert body["goal_hash"].startswith("sha256:")
    assert goal not in body.values()

    assert len(calls) == 2
    assert calls[0][0:2] == ("GET", "/server_info")
    launch_payload = calls[1][2]["json"]
    assert launch_payload["worktree"] is True
    assert launch_payload["workspace"] == {
        "kind": "LocalWorkspace",
        "working_dir": "/workspace/repos/XDSawyerLoL/Human-Agency-Engine",
    }
    assert launch_payload["agent_profile_id"] == settings.software_agent_agent_profile_id
    mission = launch_payload["initial_message"]["content"][0]["text"]
    assert goal in mission
    assert "Never push, merge, deploy, publish" in mission
    assert "pytest -q tests/test_software_agent.py" in mission

    repeated = client.post("/v1/execution/software-agent/runs", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["run_id"] == body["run_id"]
    assert len(calls) == 2

    collision = client.post(
        "/v1/execution/software-agent/runs",
        json={**payload, "goal": "A different software mission with the same idempotency key."},
    )
    assert collision.status_code == 409

    db = SessionLocal()
    try:
        stored = db.query(SoftwareAgentRun).filter(SoftwareAgentRun.run_id == body["run_id"]).one()
        assert stored.goal_hash == body["goal_hash"]
        assert not hasattr(stored, "goal")
    finally:
        db.close()

    columns = {column["name"] for column in inspect(engine).get_columns("software_agent_runs")}
    assert "goal" not in columns
    assert "goal_hash" in columns


def test_profile_id_file_is_resolved_at_launch_time(monkeypatch, tmp_path):
    _configure(monkeypatch)
    profile_id = str(uuid.uuid4())
    profile_file = tmp_path / "agent-profile-id"
    profile_file.write_text(profile_id + "\n", encoding="utf-8")
    monkeypatch.setattr(settings, "software_agent_agent_profile_id", "")
    monkeypatch.setattr(
        settings,
        "software_agent_agent_profile_id_file",
        str(profile_file),
    )

    assert _resolved_agent_profile_id(required=True) == profile_id
    capabilities = client.get("/v1/execution/software-agent/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["configured"] is True
    assert capabilities.json()["agent_profile_source"] == "file"

    preflight_id = _authorized_preflight(
        "software-agent-profile-file-e",
        "software-agent-dry-run-profile-file-0001",
    )
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and path == "/server_info":
            return {"conversation_runtime": "docker"}
        if method == "POST" and path == "/api/conversations":
            return {
                "id": "33333333-3333-4333-8333-333333333333",
                "execution_status": "running",
            }
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(SoftwareAgentSandboxService, "_request", fake_request)
    launched = client.post(
        "/v1/execution/software-agent/runs",
        json={
            "preflight_id": preflight_id,
            "idempotency_key": "software-agent-idempotency-profile-file-0001",
            "repository": "XDSawyerLoL/Human-Agency-Engine",
            "goal": "Verify that the runtime-created OpenHands profile UUID is consumed safely.",
        },
    )
    assert launched.status_code == 200, launched.text
    assert calls[1][2]["json"]["agent_profile_id"] == profile_id


def test_missing_profile_id_file_fails_closed(monkeypatch, tmp_path):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "software_agent_agent_profile_id", "")
    monkeypatch.setattr(
        settings,
        "software_agent_agent_profile_id_file",
        str(tmp_path / "missing-agent-profile-id"),
    )

    assert _resolved_agent_profile_id(required=False) == ""
    capabilities = client.get("/v1/execution/software-agent/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["configured"] is False


def test_launch_rejects_non_docker_openhands_runtime(monkeypatch):
    _configure(monkeypatch)
    preflight_id = _authorized_preflight(
        "software-agent-runtime-d",
        "software-agent-dry-run-runtime-0001",
    )

    def fake_request(self, method, path, **kwargs):
        assert method == "GET"
        assert path == "/server_info"
        return {"conversation_runtime": "local"}

    monkeypatch.setattr(SoftwareAgentSandboxService, "_request", fake_request)
    response = client.post(
        "/v1/execution/software-agent/runs",
        json={
            "preflight_id": preflight_id,
            "idempotency_key": "software-agent-idempotency-runtime-0001",
            "repository": "XDSawyerLoL/Human-Agency-Engine",
            "goal": "Attempt a valid mission against a non-isolated OpenHands runtime.",
        },
    )
    assert response.status_code == 400
    assert "conversation_runtime=docker" in response.text


def test_launch_rejects_repository_outside_allowlist(monkeypatch):
    _configure(monkeypatch)
    preflight_id = _authorized_preflight(
        "software-agent-allowlist-b",
        "software-agent-dry-run-allowlist-0001",
    )

    response = client.post(
        "/v1/execution/software-agent/runs",
        json={
            "preflight_id": preflight_id,
            "idempotency_key": "software-agent-idempotency-allowlist-0001",
            "repository": "OtherOwner/OtherRepo",
            "goal": "Make an otherwise valid sandboxed change to an unauthorized repository.",
        },
    )
    assert response.status_code == 400
    assert "allow-listed" in response.text


def test_refresh_returns_but_does_not_persist_final_response_and_interrupts(monkeypatch):
    _configure(monkeypatch)
    preflight_id = _authorized_preflight(
        "software-agent-refresh-c",
        "software-agent-dry-run-refresh-0001",
    )
    conversation_id = "22222222-2222-4222-8222-222222222222"
    mode = {"state": "running"}

    def fake_request(self, method, path, **kwargs):
        if method == "GET" and path == "/server_info":
            return {"conversation_runtime": "docker"}
        if method == "POST" and path == "/api/conversations":
            return {"id": conversation_id, "execution_status": "running"}
        if method == "GET" and path == f"/api/conversations/{conversation_id}":
            return {"id": conversation_id, "execution_status": mode["state"]}
        if method == "GET" and path == f"/api/conversations/{conversation_id}/agent_final_response":
            return {"response": "Changed app/example.py; pytest passed; rollback is git worktree removal."}
        if method == "POST" and path == f"/api/conversations/{conversation_id}/interrupt":
            return {"success": True}
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(SoftwareAgentSandboxService, "_request", fake_request)
    launched = client.post(
        "/v1/execution/software-agent/runs",
        json={
            "preflight_id": preflight_id,
            "idempotency_key": "software-agent-idempotency-refresh-0001",
            "repository": "XDSawyerLoL/Human-Agency-Engine",
            "goal": "Exercise refresh and interrupt behavior for a sandboxed software mission.",
        },
    )
    assert launched.status_code == 200, launched.text
    run_id = launched.json()["run_id"]

    interrupted = client.post(f"/v1/execution/software-agent/runs/{run_id}/interrupt")
    assert interrupted.status_code == 200, interrupted.text
    assert interrupted.json()["status"] == "interrupted"
    assert interrupted.json()["execution_status"] == "paused"

    mode["state"] = "finished"
    refreshed = client.post(f"/v1/execution/software-agent/runs/{run_id}/refresh")
    assert refreshed.status_code == 200, refreshed.text
    result = refreshed.json()
    assert result["status"] == "completed"
    assert result["final_response"].startswith("Changed app/example.py")
    assert result["final_response_persisted"] is False
    assert result["final_response_hash"].startswith("sha256:")

    db = SessionLocal()
    try:
        stored = db.query(SoftwareAgentRun).filter(SoftwareAgentRun.run_id == run_id).one()
        assert stored.final_response_hash == result["final_response_hash"]
        assert not hasattr(stored, "final_response")
    finally:
        db.close()
