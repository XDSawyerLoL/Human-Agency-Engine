from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_recurring_expense_opportunity():
    uid = "test-user-core"

    user_response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "monthly_income": 1600,
            "monthly_fixed_costs": 1200,
            "liquid_cash": 500,
            "minimum_cash_buffer": 150,
        },
    )
    assert user_response.status_code == 200

    signal_response = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "manual",
            "type": "recurring_expense",
            "payload": {
                "merchant": "Example",
                "monthly_amount": 12.99,
                "usage_score": 0.1,
            },
        },
    )
    assert signal_response.status_code == 200

    result = client.post(f"/v1/users/{uid}/engine/run")
    assert result.status_code == 200
    data = result.json()
    assert any(item["category"] == "money" for item in data)
    assert data[0]["care_status"] in {"approved", "review"}
