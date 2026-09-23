from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.services.horizon_aura_bridge import HorizonAuraBridgeService


client = TestClient(app)


def test_aura_bridge_preserves_horizon_truth_boundaries():
    db = SessionLocal()
    try:
        body = HorizonAuraBridgeService(db).snapshot()
        assert body["bridge"] == "horizon-aura-bridge-v1"
        assert body["critical_semantics"]["aura_must_preserve_epistemic_status"] is True
        assert body["critical_semantics"]["emerging_hypothesis_may_trigger_irreversible_action"] is False
        assert body["critical_semantics"]["scores_are_not_probabilities"] is True
        assert body["summary"]["signals"] == len(body["signals"])
        for signal in body["signals"]:
            assert signal["signal_id"]
            assert signal["entity_key"]
            assert signal["aura_event"] in {
                "horizon.world.confirmed",
                "horizon.world.emerging",
                "horizon.personal.forecast",
            }
            assert signal["payload"].get("probability") is None
    finally:
        db.close()


def test_aura_bridge_routes_are_mounted():
    capabilities = client.get("/v1/horizon/aura/capabilities")
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["supports_personal_context"] is True

    feed = client.get("/v1/horizon/aura/feed")
    assert feed.status_code == 200, feed.text
    assert feed.json()["bridge"] == "horizon-aura-bridge-v1"
