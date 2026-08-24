from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.services.horizon_cold_response import HorizonColdResponseLibraryService
from app.services.horizon_mechanism_registry import (
    HorizonMechanismRegistryService,
    historically_calibratable_event_types,
)
from app.services.horizon_response_library import HorizonResponseLibraryService


client = TestClient(app)


def test_mechanism_registry_separates_plausible_behavior_from_historical_calibration():
    db = SessionLocal()
    try:
        HorizonResponseLibraryService(db).sync_builtins()
        HorizonColdResponseLibraryService(db).sync()
        result = HorizonMechanismRegistryService(db).snapshot()
        by_key = {item["mechanism_key"]: item for item in result["mechanisms"]}

        heat = by_key["regional-heat-to-cooling-load-v1"]
        cold = by_key["regional-cold-to-heating-load-v1"]
        supply = by_key["supply-risk-to-precautionary-buying-v1"]
        transport = by_key["transit-disruption-to-mode-substitution-v1"]

        assert heat["calibration_readiness"] == "historically_calibratable"
        assert cold["calibration_readiness"] == "historically_calibratable"
        assert heat["strategies_configured"] is True
        assert cold["strategies_configured"] is True
        assert heat["trigger_replay"]["point_in_time"] is True
        assert heat["outcome_replay"]["point_in_time"] is True

        assert supply["calibration_readiness"] == "outcome_replay_only"
        assert supply["outcome_replay"]["status"] == "implemented"
        assert supply["outcome_replay"]["point_in_time"] is True
        assert "fuel_stockout_pressure" in supply["outcome_signal_types"]
        assert supply["trigger_replay"]["status"] == "missing"

        assert transport["calibration_readiness"] == "behavior_hypothesis_only"
        assert transport["trigger_replay"]["status"] == "missing"
        assert transport["outcome_replay"]["status"] == "missing"

        assert set(result["historically_calibratable_event_types"]) == {
            "extreme_heat_region",
            "extreme_cold_region",
        }
        assert result["critical_semantics"]["behavior_pattern_is_calibration_proof"] is False
        assert result["critical_semantics"]["numeric_probabilities_enabled"] is False
    finally:
        db.close()


def test_historical_event_type_set_is_derived_from_mechanism_contracts():
    assert historically_calibratable_event_types() == {
        "extreme_heat_region",
        "extreme_cold_region",
    }


def test_mechanism_registry_endpoint_is_mounted_on_dedicated_horizon_api():
    db = SessionLocal()
    try:
        HorizonResponseLibraryService(db).sync_builtins()
        HorizonColdResponseLibraryService(db).sync()
    finally:
        db.close()

    response = client.get("/v1/horizon/world/mechanisms")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine"] == "horizon-mechanism-registry-v0.1"
    assert len(body["mechanisms"]) >= 5
    assert body["critical_semantics"]["point_in_time_replay_required"] is True

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mechanism_registry_supported"] is True
