from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.personal_agent_models import PersonalAgentMission


client = TestClient(app)


def _create_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2200,
            "monthly_fixed_costs": 1200,
            "liquid_cash": 1000,
            "minimum_cash_buffer": 200,
        },
    )
    assert response.status_code == 200, response.text


def test_personal_agent_mission_is_encrypted_and_manual_run_is_audited(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(settings, "personal_agent_enabled", False)
    uid = "personal-agent-runtime-a"
    _create_user(uid)

    created = client.post(
        f"/v1/personal-agent/users/{uid}/missions",
        json={
            "title": "Refresh my connected context",
            "goal": "Synchronize my available read-only connectors and report only operational metadata.",
            "task_type": "connector_sync",
            "autonomy_level": "prepare",
            "required_capabilities": [],
            "task_payload": {"private_note": "do-not-return-this-value"},
            "trigger_type": "manual",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["goal_persisted"] == "encrypted"
    assert body["task_payload_persisted"] == "encrypted"
    assert body["goal_hash"].startswith("sha256:")
    assert "Synchronize my available" not in created.text
    assert "do-not-return-this-value" not in created.text

    mission_id = body["mission_id"]
    run = client.post(
        f"/v1/personal-agent/users/{uid}/missions/{mission_id}/run",
        json={"trigger": "manual"},
    )
    assert run.status_code == 200, run.text
    run_body = run.json()
    assert run_body["status"] == "succeeded"
    assert run_body["external_dispatch"] is False
    assert run_body["authorization_required"] is False

    history = client.get(
        f"/v1/personal-agent/users/{uid}/missions/{mission_id}/runs"
    )
    assert history.status_code == 200
    assert history.json()[0]["run_id"] == run_body["run_id"]

    db = SessionLocal()
    try:
        stored = (
            db.query(PersonalAgentMission)
            .filter(PersonalAgentMission.mission_id == mission_id)
            .one()
        )
        assert "Synchronize my available" not in stored.encrypted_goal
        assert "do-not-return-this-value" not in stored.encrypted_task_payload
        assert stored.run_count == 1
    finally:
        db.close()

    columns = {column["name"] for column in inspect(engine).get_columns("personal_agent_missions")}
    assert "goal" not in columns
    assert "task_payload" not in columns
    assert "encrypted_goal" in columns
    assert "encrypted_task_payload" in columns


def test_capability_surface_does_not_claim_unconfigured_computer_or_browser(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode("ascii"))
    uid = "personal-agent-capabilities-b"
    _create_user(uid)

    response = client.get(f"/v1/personal-agent/users/{uid}/capabilities")
    assert response.status_code == 200, response.text
    capabilities = response.json()["capabilities"]
    assert capabilities["browser_use"]["available"] is False
    assert capabilities["computer_use"]["available"] is False
    assert capabilities["slack"]["available"] is False
    assert capabilities["sms"]["available"] is False


def test_interval_mission_can_be_claimed_by_scheduler(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode("ascii"))
    uid = "personal-agent-scheduler-c"
    _create_user(uid)

    created = client.post(
        f"/v1/personal-agent/users/{uid}/missions",
        json={
            "title": "Periodic agency cycle",
            "goal": "Periodically refresh safe read-only context and run the local decision pipeline.",
            "task_type": "agency_cycle",
            "autonomy_level": "prepare",
            "trigger_type": "interval",
            "interval_seconds": 60,
            "max_runs": 1,
            "start_immediately": True,
        },
    )
    assert created.status_code == 200, created.text

    from app.services.personal_agent import PersonalAgentService

    db = SessionLocal()
    try:
        results = PersonalAgentService(db).run_due(limit=5)
        assert len(results) == 1
        assert results[0]["status"] == "succeeded"
        mission = (
            db.query(PersonalAgentMission)
            .filter(PersonalAgentMission.mission_id == created.json()["mission_id"])
            .one()
        )
        assert mission.status == "completed"
        assert mission.run_count == 1
    finally:
        db.close()
