from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.services.horizon_response_library import HorizonResponseLibraryService
from app.services.horizon_sources import HorizonSourceService
from app.services.horizon_world_coverage import HorizonWorldCoverageService


client = TestClient(app)


def test_world_coverage_makes_domain_imbalance_explicit_and_never_reports_probability():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        HorizonResponseLibraryService(db).sync_builtins()
        result = HorizonWorldCoverageService(db).snapshot()
        by_domain = {item["domain"]: item for item in result["domains"]}

        assert result["product_scope"] == "domain_agnostic_personal_world_anticipation"
        assert by_domain["weather_climate"]["current_maturity"] == "historically_calibratable"
        assert by_domain["economy_labor"]["current_maturity"] == "discovery_only"
        assert by_domain["geopolitics_security"]["current_maturity"] == "discovery_only"
        assert by_domain["cyber_technology"]["current_maturity"] == "discovery_only"
        assert by_domain["personal_context"]["current_maturity"] == "personalized"
        assert "builtin-transit-disruption-mode-substitution-v1" in by_domain["transport_mobility"]["behavior_pattern_keys"]
        assert result["critical_semantics"]["weather_is_product_boundary"] is False
        assert result["critical_semantics"]["diagnostic_maturity_is_probability"] is False
        assert result["critical_semantics"]["numeric_probabilities_enabled"] is False
    finally:
        db.close()


def test_world_coverage_is_mounted_on_dedicated_horizon_api():
    response = client.get("/v1/horizon/world/coverage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine"] == "horizon-world-coverage-v0.1"
    assert len(body["domains"]) >= 12

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["world_coverage_inventory_supported"] is True
    assert health.json()["multi_domain_discovery_supported"] is True
    assert health.json()["weather_is_product_boundary"] is False
