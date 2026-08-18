import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.delegation_models import AgentSigningIdentity, DelegationGrant, DelegationUse
from app.main import app
from app.models import User
from app.synthesis_models import CandidateIntervention

client = TestClient(app)


def _setup(uid: str) -> int:
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")
    user = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2000,
            "monthly_fixed_costs": 1200,
            "liquid_cash": 800,
            "minimum_cash_buffer": 150,
        },
    )
    assert user.status_code == 200
    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Keep delegation minimal and revocable.",
            "principles": ["minimal disclosure"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
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
            source_ref="delegation-privacy-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Minimal disclosure candidate",
            rationale="Synthetic ready candidate for deletion/export verification.",
            intervention={"type": "prepare_offer", "reversible": True},
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
        return candidate.id
    finally:
        db.close()


def test_delegation_export_is_non_reusable_and_user_delete_removes_all_secret_state():
    uid = "delegation-sovereignty-a"
    candidate_id = _setup(uid)
    issued = client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": "prepare",
            "audience": "external-agent.example",
            "expires_in_seconds": 600,
            "max_uses": 2,
            "constraints": {"purpose": "prepare an offer"},
            "confirm": f"ISSUE {candidate_id} prepare",
        },
    )
    assert issued.status_code == 200
    token = issued.json()["proof"]["token"]
    grant_public_id = issued.json()["grant"]["grant_id"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]

    consumed = client.post(
        "/v1/delegations/consume",
        json={
            "token": token,
            "audience": "external-agent.example",
            "request_id": "privacy-request-0001",
            "action_fingerprint": fingerprint,
        },
    )
    assert consumed.status_code == 200

    exported = client.get(f"/v1/delegations/users/{uid}/export")
    assert exported.status_code == 200
    body = exported.json()
    assert body["identities"]
    assert body["grants"]
    assert body["uses"]
    assert body["private_keys_included"] is False
    assert body["bearer_tokens_included"] is False
    assert body["self_graph_included"] is False
    assert body["raw_intents_included"] is False
    assert body["raw_personal_mandate_included"] is False
    serialized = str(body)
    assert token not in serialized
    assert "encrypted_private_key" not in serialized

    db = SessionLocal()
    try:
        user_row = db.query(User).filter(User.external_id == uid).one()
        deleted_user_id = user_row.id
        identity_ids = [
            row[0]
            for row in db.query(AgentSigningIdentity.id)
            .filter(AgentSigningIdentity.user_id == deleted_user_id)
            .all()
        ]
        grant_row = (
            db.query(DelegationGrant)
            .filter(DelegationGrant.grant_id == grant_public_id)
            .one()
        )
        deleted_grant_id = grant_row.id
        use_ids = [
            row[0]
            for row in db.query(DelegationUse.id)
            .filter(DelegationUse.grant_id == deleted_grant_id)
            .all()
        ]
        assert identity_ids
        assert use_ids
    finally:
        db.close()

    deleted = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": f"DELETE {uid}"},
    )
    assert deleted.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == deleted_user_id).count() == 0
        assert db.query(AgentSigningIdentity).filter(AgentSigningIdentity.id.in_(identity_ids)).count() == 0
        assert db.query(DelegationGrant).filter(DelegationGrant.id == deleted_grant_id).count() == 0
        assert db.query(DelegationUse).filter(DelegationUse.id.in_(use_ids)).count() == 0
    finally:
        db.close()
