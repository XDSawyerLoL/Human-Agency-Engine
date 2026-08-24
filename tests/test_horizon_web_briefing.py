from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.services.horizon_briefing import HorizonWorldBriefingService
from app.services.horizon_response_library import HorizonResponseLibraryService
from app.services.horizon_sources import HorizonSourceService


client = TestClient(app)


def test_world_briefing_exposes_multidomain_truth_boundaries():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        HorizonResponseLibraryService(db).sync_builtins()
        body = HorizonWorldBriefingService(db).snapshot()
        by_domain = {item["domain"]: item for item in body["domains"]}

        assert body["product_scope"] == "domain_agnostic_personal_world_anticipation"
        assert "weather_climate" in by_domain
        assert "social_collective_behavior" in by_domain
        assert "economy_labor" in by_domain
        assert by_domain["weather_climate"]["macro_category"] == "weather"
        assert by_domain["social_collective_behavior"]["macro_category"] == "social"
        assert by_domain["economy_labor"]["macro_category"] == "economy"
        assert body["critical_semantics"]["unconfirmed_hypothesis_is_fact"] is False
        assert body["critical_semantics"]["diagnostic_score_is_probability"] is False
        assert body["summary"]["numeric_probabilities_enabled"] is False
    finally:
        db.close()


def test_world_briefing_route_and_web_cockpit_are_mounted():
    response = client.get("/v1/horizon/world/briefing")
    assert response.status_code == 200, response.text
    assert response.json()["engine"] == "horizon-world-briefing-v0.1"

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {302, 307}
    assert root.headers["location"] == "/ui/"

    ui = client.get("/ui/")
    assert ui.status_code == 200
    assert "HORIZON" in ui.text
    assert "Météo" in ui.text
    assert "Social" in ui.text
    assert "Économie" in ui.text
