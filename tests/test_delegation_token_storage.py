import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import settings
from app.db import SessionLocal, engine
from app.delegation_models import DelegationGrant
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
            "monthly_income": 2100,
            "monthly_fixed_costs": 1200,
            "liquid_cash": 900,
            "minimum_cash_buffer": 150,
        },
    )
    assert user.status_code == 200
    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Keep delegation credentials non-recoverable from storage.",
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
            source_ref="delegation-storage-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Storage-safe delegation candidate",
            rationale="Synthetic candidate used to test bearer-proof storage only.",
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


def test_issued_delegation_returns_proof_but_database_stores_only_hash():
    uid = "delegation-storage-a"
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
    assert issued.status_code == 200, issued.text
    token = issued.json()["proof"]["token"]
    grant_id = issued.json()["grant"]["grant_id"]
    assert token.count(".") == 2

    db = SessionLocal()
    try:
        grant = db.query(DelegationGrant).filter(DelegationGrant.grant_id == grant_id).one()
        assert grant.token_hash.startswith("sha256:")
        assert len(grant.token_hash) == 71
        assert grant.token_hash != token
        assert token not in str(grant.__dict__)
        assert "token" not in grant.__dict__
    finally:
        db.close()

    columns = {column["name"] for column in inspect(engine).get_columns("delegation_grants")}
    assert "token_hash" in columns
    assert "token" not in columns

    verified = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "external-agent.example"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True


def test_modified_or_unregistered_proof_cannot_match_stored_hash():
    uid = "delegation-storage-b"
    candidate_id = _setup(uid)
    issued = client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": "prepare",
            "audience": "external-agent.example",
            "expires_in_seconds": 600,
            "max_uses": 1,
            "constraints": {},
            "confirm": f"ISSUE {candidate_id} prepare",
        },
    )
    assert issued.status_code == 200
    token = issued.json()["proof"]["token"]

    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    verified = client.post(
        "/v1/delegations/verify",
        json={"token": tampered, "audience": "external-agent.example"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is False
