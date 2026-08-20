from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app as horizon_app
from app.horizon_collector_models import (
    HorizonCollectorCycle,
    HorizonCollectorLease,
    HorizonCollectorSourceState,
)
from app.services.horizon_collector import HorizonCollectorService
from app.services.horizon_live_convergence import HorizonLiveConvergenceService


client = TestClient(horizon_app)


def _reset(db):
    db.query(HorizonCollectorCycle).delete(synchronize_session=False)
    db.query(HorizonCollectorSourceState).delete(synchronize_session=False)
    db.query(HorizonCollectorLease).delete(synchronize_session=False)
    db.commit()


def _only_due(db, source_key: str, now: datetime):
    service = HorizonCollectorService(db)
    states = service._ensure_states(now)
    for row in states:
        row.next_due_at = now + timedelta(days=1)
    target = next(row for row in states if row.source_key == source_key)
    target.next_due_at = now - timedelta(seconds=1)
    db.commit()
    return service


def test_collector_polls_only_due_source_and_persists_success(monkeypatch):
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        _reset(db)
        service = _only_due(db, "gdelt", now)

        def fake_poll(self, request):  # noqa: ARG001
            assert request.include_gdelt is True
            assert request.include_gdacs is False
            assert request.include_meteofrance is False
            assert request.include_meteoalarm is False
            assert request.include_fuel is False
            assert request.include_rte_realtime is False
            assert request.include_vigicrues is False
            assert request.include_sncf is False
            assert request.build_event_graph is False
            return {
                "sources": [{"source": "gdelt-doc-2", "ok": True, "result": {"observations": 3}}],
                "provisional_refresh": None,
                "weather_chain": {"source": "weather-chain-reconciliation", "ok": True, "result": {}},
                "convergence_snapshot_errors": [],
                "event_graph": None,
            }

        monkeypatch.setattr(HorizonLiveConvergenceService, "poll", fake_poll)
        result = service.run_due(owner_id="collector-test-a")

        assert result["status"] == "success"
        assert result["due_sources"] == ["gdelt"]
        assert result["critical_semantics"]["single_active_collector_lease"] is True
        assert result["critical_semantics"]["numeric_probabilities_enabled"] is False

        state = db.query(HorizonCollectorSourceState).filter_by(source_key="gdelt").one()
        assert state.last_attempt_at is not None
        assert state.last_success_at is not None
        assert state.consecutive_failures == 0
        assert state.next_due_at > state.last_attempt_at
        cycle = db.query(HorizonCollectorCycle).one()
        assert cycle.status == "success"
        assert cycle.due_sources == ["gdelt"]
    finally:
        _reset(db)
        db.close()


def test_collector_lease_blocks_second_owner():
    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        _reset(db1)
        acquired = HorizonCollectorService(db1).acquire_lease("leader-a")
        assert acquired["acquired"] is True

        result = HorizonCollectorService(db2).run_due(owner_id="leader-b")
        assert result["status"] == "standby"
        assert result["leader"]["owner_id"] == "leader-a"
        assert result["numeric_probabilities_enabled"] is False
    finally:
        db2.close()
        _reset(db1)
        db1.close()


def test_collector_failure_uses_bounded_backoff(monkeypatch):
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        _reset(db)
        service = _only_due(db, "gdelt", now)

        def failed_poll(self, request):  # noqa: ARG001
            return {
                "sources": [{"source": "gdelt-doc-2", "ok": False, "error": "provider unavailable"}],
                "provisional_refresh": None,
                "weather_chain": {"source": "weather-chain-reconciliation", "ok": True, "result": {}},
                "convergence_snapshot_errors": [],
                "event_graph": None,
            }

        monkeypatch.setattr(HorizonLiveConvergenceService, "poll", failed_poll)
        first = service.run_due(owner_id="collector-test-backoff")
        assert first["status"] == "failed"
        state = db.query(HorizonCollectorSourceState).filter_by(source_key="gdelt").one()
        first_attempt = state.last_attempt_at
        first_due = state.next_due_at
        assert state.consecutive_failures == 1
        assert first_due >= first_attempt + timedelta(seconds=state.cadence_seconds)

        second = service.run_due(
            owner_id="collector-test-backoff",
            force_sources=["gdelt"],
            trigger="test",
        )
        assert second["status"] == "failed"
        db.refresh(state)
        assert state.consecutive_failures == 2
        assert state.next_due_at >= state.last_attempt_at + timedelta(seconds=state.cadence_seconds * 2)
    finally:
        _reset(db)
        db.close()


def test_collector_routes_are_on_dedicated_horizon_api():
    response = client.get("/v1/horizon/collector/status?cycle_limit=2")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine"] == "horizon-permanent-collector-v0.1"
    assert payload["numeric_probabilities_enabled"] is False
    assert {item["source_key"] for item in payload["sources"]} >= {
        "gdelt", "gdacs", "meteofrance", "meteoalarm", "fuel", "rte_realtime", "vigicrues", "sncf", "windy", "synthesis"
    }

    invalid = client.post(
        "/v1/horizon/collector/run-due",
        json={"owner_id": "test", "force_sources": ["not-a-source"]},
    )
    assert invalid.status_code == 422, invalid.text
