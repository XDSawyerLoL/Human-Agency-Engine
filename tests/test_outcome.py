from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_outcome_closes_learning_loop():
    uid = "test-user-outcome"
    client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "liquid_cash": 500,
            "minimum_cash_buffer": 150,
        },
    )
    client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "manual",
            "type": "recurring_expense",
            "payload": {
                "merchant": "Example",
                "monthly_amount": 9.99,
                "usage_score": 0.1,
            },
        },
    )
    opportunities = client.post(f"/v1/users/{uid}/engine/run").json()
    opportunity_id = opportunities[0]["id"]

    outcome = client.put(
        f"/v1/opportunities/{opportunity_id}/outcome",
        json={
            "useful": True,
            "accepted": True,
            "executed": True,
            "realized_value": 9.99,
            "feedback": "subscription cancelled",
        },
    )

    assert outcome.status_code == 200
    data = outcome.json()
    assert data["status"] == "executed"
    assert data["realized_value"] == 9.99
    assert data["useful"] is True
