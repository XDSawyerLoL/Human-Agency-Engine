from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2000,
            "monthly_fixed_costs": 1200,
            "liquid_cash": 600,
            "minimum_cash_buffer": 150,
        },
    )
    assert response.status_code == 200


def test_personal_mandate_versions_and_limits_proactivity():
    uid = "test-user-mandate-v1"
    _create_user(uid)

    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Increase my options without creating financial fragility.",
            "principles": ["user control", "no paid ranking"],
            "constraints": {},
            "autonomy": {"default": "suggest"},
            "notification_policy": {
                # Deliberately below the observational evidence cap so this test
                # exercises max_per_day rather than the scientific confidence gate.
                "min_confidence": 0.5,
                "max_per_day": 1,
                "category_cooldown_hours": 24,
                "quiet_hours": {"start": 23, "end": 7},
            },
        },
    )
    assert mandate.status_code == 200
    assert mandate.json()["version"] == 1

    updated = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            **mandate.json(),
            "mission": "Protect my floor and increase my future options.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    for merchant in ("Example One", "Example Two"):
        signal = client.post(
            f"/v1/users/{uid}/signals",
            json={
                "source": "manual",
                "type": "recurring_expense",
                "payload": {
                    "merchant": merchant,
                    "monthly_amount": 15.0,
                    "usage_score": 0.1,
                },
            },
        )
        assert signal.status_code == 200

    engine = client.post(f"/v1/users/{uid}/engine/run")
    assert engine.status_code == 200
    assert len(engine.json()) == 2

    notifications = client.get(
        f"/v1/users/{uid}/notifications",
        params={"include_suppressed": "true"},
    )
    assert notifications.status_code == 200
    statuses = [item["status"] for item in notifications.json()]
    assert statuses.count("queued") == 1
    assert statuses.count("suppressed") == 1
    suppressed = next(item for item in notifications.json() if item["status"] == "suppressed")
    assert suppressed["suppression_reason"]


def test_privacy_export_excludes_secrets_and_delete_is_complete():
    uid = "test-user-privacy-v1"
    _create_user(uid)

    intent = client.post(
        f"/v1/users/{uid}/intents",
        json={
            "kind": "career",
            "statement": "Improve my professional options",
            "priority": 0.8,
        },
    )
    assert intent.status_code == 200

    exported = client.get(f"/v1/users/{uid}/export")
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["secrets_included"] is False
    assert "encrypted_token_json" not in str(payload)
    assert payload["user"]["external_id"] == uid
    assert len(payload["intents"]) == 1

    rejected = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": uid},
    )
    assert rejected.status_code == 400

    deleted = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": f"DELETE {uid}"},
    )
    assert deleted.status_code == 200

    missing = client.get(f"/v1/users/{uid}/export")
    assert missing.status_code == 404


def test_impact_reports_realized_value_and_usefulness():
    uid = "test-user-impact-v1"
    _create_user(uid)

    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "manual",
            "type": "recurring_expense",
            "payload": {
                "merchant": "Impact Example",
                "monthly_amount": 20.0,
                "usage_score": 0.1,
            },
        },
    )
    assert signal.status_code == 200

    engine = client.post(f"/v1/users/{uid}/engine/run")
    assert engine.status_code == 200
    opportunity_id = engine.json()[0]["id"]

    outcome = client.put(
        f"/v1/opportunities/{opportunity_id}/outcome",
        json={
            "useful": True,
            "accepted": True,
            "executed": True,
            "realized_value": 20.0,
            "feedback": "Cancelled after review",
        },
    )
    assert outcome.status_code == 200

    impact = client.get(f"/v1/users/{uid}/impact")
    assert impact.status_code == 200
    data = impact.json()
    assert data["useful_count"] == 1
    assert data["useful_rate"] == 1.0
    assert data["executed_count"] == 1
    assert data["realized_value"] == 20.0
