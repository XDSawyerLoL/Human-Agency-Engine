from uuid import uuid4

from fastapi.testclient import TestClient

from app.horizon_api import app


client = TestClient(app)


def test_dedicated_horizon_api_exposes_health_and_horizon_only_surface():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "horizon-predictive-intelligence"
    assert health.json()["legacy_action_surface_exposed"] is False

    ready = client.get("/ready")
    assert ready.status_code == 200

    capabilities = client.get("/v1/horizon/convergence/capabilities")
    assert capabilities.status_code == 200, capabilities.text

    paths = {getattr(route, "path", "") for route in app.routes}
    forbidden_fragments = (
        "/settlement",
        "/delegation",
        "/market",
        "/allocation",
        "/execution",
        "/collective",
    )
    for path in paths:
        if path.startswith("/v1"):
            assert path.startswith("/v1/horizon"), path
            assert not any(fragment in path for fragment in forbidden_fragments), path

    assert client.get("/v1/users/nobody/mandate").status_code == 404
    assert client.post("/v1/settlement-permits/verify", json={}).status_code == 404


def test_dedicated_horizon_context_can_seed_personal_forecast_context():
    external_id = f"horizon-hostinger-{uuid4().hex[:12]}"
    user = client.put(
        f"/v1/horizon/context/users/{external_id}",
        json={
            "external_id": external_id,
            "country": "FR",
            "currency": "EUR",
            "timezone": "Europe/Paris",
            "preferences": {},
        },
    )
    assert user.status_code == 200, user.text
    assert user.json()["created"] is True

    state = client.post(
        f"/v1/horizon/context/users/{external_id}/state/facts",
        json={
            "domain": "location",
            "key": "home",
            "value": {"country": "FR", "region": "11"},
            "source": "user",
            "confidence": 1.0,
        },
    )
    assert state.status_code == 200, state.text
    assert state.json()["key"] == "home"

    intent = client.post(
        f"/v1/horizon/context/users/{external_id}/intents",
        json={
            "kind": "resilience",
            "statement": "Anticiper les perturbations matérielles qui peuvent m'affecter.",
            "target": {"country": "FR"},
            "priority": 0.9,
        },
    )
    assert intent.status_code == 200, intent.text
    assert intent.json()["active"] is True
