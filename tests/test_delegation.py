import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User
from app.synthesis_models import CandidateIntervention

client = TestClient(app)


def configure_signing_key():
    settings.token_encryption_key = Fernet.generate_key().decode("ascii")


def make_user(uid: str, *, allow_execute: bool = False):
    configure_signing_key()
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2200,
            "monthly_fixed_costs": 1300,
            "liquid_cash": 900,
            "minimum_cash_buffer": 150,
        },
    )
    assert response.status_code == 200
    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Increase options while preserving explicit human control.",
            "principles": ["minimal disclosure", "reversible first"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": allow_execute},
            "notification_policy": {},
        },
    )
    assert mandate.status_code == 200


def ready_candidate(uid: str, *, reversible: bool = True) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.external_id == uid).one()
        candidate = CandidateIntervention(
            user_id=user.id,
            candidate_key=uuid.uuid4().hex,
            source_type="test",
            source_ref="delegation-test",
            hypothesis_ids=[],
            intent_ids=[],
            name="Synthetic bounded intervention",
            rationale="Ready candidate created only to isolate proof-of-mandate tests.",
            intervention={
                "type": "synthetic_reversible_action" if reversible else "synthetic_irreversible_action",
                "reversible": reversible,
                "lock_in_days": 0 if reversible else 365,
                "reversal_cost": 0 if reversible else 100,
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
            decision_status="candidate_for_reversible_pilot" if reversible else "strong_candidate_for_user_review",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate.id
    finally:
        db.close()


def issue(uid: str, candidate_id: int, *, capability: str = "prepare", max_uses: int = 1, execute_ack: bool = False):
    return client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": capability,
            "audience": "merchant-agent.example",
            "expires_in_seconds": 600,
            "max_uses": max_uses,
            "constraints": {
                "category": "synthetic",
                "purpose": "prepare a bounded offer",
            },
            "confirm": f"ISSUE {candidate_id} {capability}",
            "execute_ack": execute_ack,
        },
    )


def test_signed_grant_discloses_minimum_and_verifies_for_exact_audience():
    uid = "delegation-signature-a"
    make_user(uid)
    candidate_id = ready_candidate(uid)

    issued = issue(uid, candidate_id, capability="prepare", max_uses=2)
    assert issued.status_code == 200
    body = issued.json()
    proof = body["proof"]
    token = proof["token"]
    claims = proof["claims"]

    assert token.count(".") == 2
    assert proof["public_jwk"]["kty"] == "OKP"
    assert proof["public_jwk"]["crv"] == "Ed25519"
    assert proof["public_jwk"]["alg"] == "EdDSA"
    assert body["privacy"] == {
        "self_graph_included": False,
        "intents_included": False,
        "raw_personal_mandate_included": False,
    }
    serialized = str(claims).lower()
    assert "external_id" not in serialized
    assert "monthly_income" not in serialized
    assert "liquid_cash" not in serialized
    assert "statement" not in serialized
    assert "mission" not in serialized
    assert claims["capability"] == "prepare"
    assert claims["aud"] == "merchant-agent.example"
    assert claims["action"]["fingerprint"].startswith("sha256:")
    assert "fingerprint" in claims["candidate"]

    verified = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "merchant-agent.example"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True

    wrong_audience = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "other-agent.example"},
    )
    assert wrong_audience.status_code == 200
    assert wrong_audience.json()["valid"] is False

    key_id = proof["public_jwk"]["kid"]
    public_key = client.get(f"/v1/delegations/keys/{key_id}")
    assert public_key.status_code == 200
    assert public_key.json()["jwk"] == proof["public_jwk"]


def test_delegation_consumption_is_bounded_and_replay_safe():
    uid = "delegation-replay-b"
    make_user(uid)
    candidate_id = ready_candidate(uid)
    issued = issue(uid, candidate_id, max_uses=2)
    assert issued.status_code == 200
    token = issued.json()["proof"]["token"]
    fingerprint = issued.json()["proof"]["claims"]["action"]["fingerprint"]

    first = client.post(
        "/v1/delegations/consume",
        json={
            "token": token,
            "audience": "merchant-agent.example",
            "request_id": "request-0001",
            "action_fingerprint": fingerprint,
            "metadata_json": {"phase": "prepare"},
        },
    )
    assert first.status_code == 200
    assert first.json()["use_count"] == 1

    replay = client.post(
        "/v1/delegations/consume",
        json={
            "token": token,
            "audience": "merchant-agent.example",
            "request_id": "request-0001",
            "action_fingerprint": fingerprint,
        },
    )
    assert replay.status_code == 409

    second = client.post(
        "/v1/delegations/consume",
        json={
            "token": token,
            "audience": "merchant-agent.example",
            "request_id": "request-0002",
            "action_fingerprint": fingerprint,
        },
    )
    assert second.status_code == 200
    assert second.json()["use_count"] == 2

    exhausted = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "merchant-agent.example"},
    )
    assert exhausted.status_code == 200
    assert exhausted.json()["valid"] is False
    assert "exhausted" in exhausted.json()["reason"]


def test_personal_mandate_change_invalidates_existing_grant():
    uid = "delegation-mandate-c"
    make_user(uid)
    candidate_id = ready_candidate(uid)
    issued = issue(uid, candidate_id)
    assert issued.status_code == 200
    token = issued.json()["proof"]["token"]

    changed = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Updated human mandate.",
            "principles": ["user control"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": False},
            "notification_policy": {},
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    verified = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "merchant-agent.example"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is False
    assert "mandate changed" in verified.json()["reason"].lower()


def test_rotation_and_revocation_invalidate_grants_but_keep_public_history():
    uid = "delegation-rotation-d"
    make_user(uid)
    candidate_id = ready_candidate(uid)
    issued = issue(uid, candidate_id)
    assert issued.status_code == 200
    token = issued.json()["proof"]["token"]
    old_key_id = issued.json()["proof"]["public_jwk"]["kid"]

    rotated = client.post(
        f"/v1/delegations/users/{uid}/identity/rotate",
        json={"confirm": f"ROTATE {uid}"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["key_id"] != old_key_id

    old_key = client.get(f"/v1/delegations/keys/{old_key_id}")
    assert old_key.status_code == 200
    assert old_key.json()["revoked_at"] is not None

    old_grant = client.post(
        "/v1/delegations/verify",
        json={"token": token, "audience": "merchant-agent.example"},
    )
    assert old_grant.status_code == 200
    assert old_grant.json()["valid"] is False

    issued_again = issue(uid, candidate_id)
    assert issued_again.status_code == 200
    grant_id = issued_again.json()["grant"]["grant_id"]
    new_token = issued_again.json()["proof"]["token"]
    revoked = client.post(
        f"/v1/delegations/users/{uid}/grants/{grant_id}/revoke",
        json={"reason": "test revocation"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    verification = client.post(
        "/v1/delegations/verify",
        json={"token": new_token, "audience": "merchant-agent.example"},
    )
    assert verification.status_code == 200
    assert verification.json()["valid"] is False
    assert "revoked" in verification.json()["reason"]


def test_execute_reversible_requires_candidate_and_mandate_authorization():
    uid = "delegation-execute-e"
    make_user(uid, allow_execute=False)
    reversible_id = ready_candidate(uid, reversible=True)

    denied_by_mandate = issue(
        uid,
        reversible_id,
        capability="execute_reversible",
        execute_ack=True,
    )
    assert denied_by_mandate.status_code == 400

    enabled = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Permit only explicit reversible execution.",
            "principles": ["reversible first"],
            "constraints": {},
            "autonomy": {"allow_execute_reversible": True},
            "notification_policy": {},
        },
    )
    assert enabled.status_code == 200

    missing_ack = issue(
        uid,
        reversible_id,
        capability="execute_reversible",
        execute_ack=False,
    )
    assert missing_ack.status_code == 400

    multi_use = issue(
        uid,
        reversible_id,
        capability="execute_reversible",
        max_uses=2,
        execute_ack=True,
    )
    assert multi_use.status_code == 400

    allowed = issue(
        uid,
        reversible_id,
        capability="execute_reversible",
        max_uses=1,
        execute_ack=True,
    )
    assert allowed.status_code == 200
    claims = allowed.json()["proof"]["claims"]
    assert claims["capability"] == "execute_reversible"
    assert claims["constraints"]["reversible_only"] is True
    assert claims["max_uses"] == 1

    irreversible_id = ready_candidate(uid, reversible=False)
    impossible = issue(
        uid,
        irreversible_id,
        capability="execute_reversible",
        execute_ack=True,
    )
    assert impossible.status_code == 400


def test_constraint_allowlist_rejects_private_over_disclosure():
    uid = "delegation-privacy-f"
    make_user(uid)
    candidate_id = ready_candidate(uid)
    response = client.post(
        f"/v1/delegations/users/{uid}/grants",
        json={
            "candidate_id": candidate_id,
            "capability": "prepare",
            "audience": "merchant-agent.example",
            "expires_in_seconds": 600,
            "max_uses": 1,
            "constraints": {"private_notes": "must never leave the sovereign model"},
            "confirm": f"ISSUE {candidate_id} prepare",
        },
    )
    assert response.status_code == 400
    assert "over-disclosing" in response.json()["detail"]
