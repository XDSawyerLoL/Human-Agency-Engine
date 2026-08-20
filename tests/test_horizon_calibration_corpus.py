from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app as horizon_app
from app.horizon_corpus_models import HorizonCalibrationCorpusRun, HorizonCalibrationCorpusSlice
from app.horizon_corpus_schemas import HorizonCalibrationCorpusBuildRequest
from app.models import User
from app.services.horizon_backfill import HorizonHistoricalBackfillService
from app.services.horizon_backtest_coverage import HorizonCoverageAwareHistoricalBacktestFactory
from app.services.horizon_corpus import HorizonCalibrationCorpusService
from app.services.horizon_rte import HorizonRteCoolingLoadBackfillService


client = TestClient(horizon_app)


def _user(db, tag: str) -> User:
    row = User(
        external_id=f"corpus-{tag}",
        country="FR",
        currency="EUR",
        timezone="Europe/Paris",
        preferences={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _cleanup_corpus(db, user_id: int):
    run_ids = [row.id for row in db.query(HorizonCalibrationCorpusRun).filter_by(user_id=user_id).all()]
    if run_ids:
        db.query(HorizonCalibrationCorpusSlice).filter(
            HorizonCalibrationCorpusSlice.run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.query(HorizonCalibrationCorpusRun).filter(
            HorizonCalibrationCorpusRun.id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.commit()


def _fake_dependencies(monkeypatch, counters: dict | None = None):
    counters = counters if counters is not None else {}
    counters.setdefault("meteo", 0)
    counters.setdefault("rte", 0)
    counters.setdefault("backtest", 0)

    def fake_meteo(self, payload, client=None):  # noqa: ARG001
        counters["meteo"] += 1
        return {
            "events_promoted": 2,
            "events_replayed": 0,
            "episodes_detected": 3,
            "errors": [],
            "replayed_existing_run": False,
        }

    def fake_rte(self, payload, client=None):  # noqa: ARG001
        counters["rte"] += 1
        return {
            "regional_heat_events_considered": 1,
            "regions": [{"region_code": "11", "coverage_complete": True}],
            "errors": [],
            "replayed_existing_run": False,
        }

    def fake_backtest(self, user, payload):  # noqa: ARG001
        counters["backtest"] += 1
        return {
            "selected_cases": 2,
            "outcomes": {"confirmed": 1, "partial": 0, "false": 1, "inconclusive": 0, "unresolved": 0},
            "skipped": {"outcome_coverage_incomplete": 0},
            "mean_predictive_lead_time_hours": 18.0,
            "replayed_existing_run": False,
        }

    monkeypatch.setattr(HorizonHistoricalBackfillService, "backfill_meteofrance_vigilance", fake_meteo)
    monkeypatch.setattr(HorizonRteCoolingLoadBackfillService, "backfill", fake_rte)
    monkeypatch.setattr(HorizonCoverageAwareHistoricalBacktestFactory, "run", fake_backtest)
    return counters


def test_corpus_builder_resumes_same_run_slice_by_slice(monkeypatch):
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    counters = _fake_dependencies(monkeypatch)
    request = HorizonCalibrationCorpusBuildRequest(
        start_at=datetime(2024, 6, 1),
        end_at=datetime(2024, 7, 20),
        slice_days=20,
        outcome_grace_days=7,
        max_slices_per_call=1,
    )
    try:
        service = HorizonCalibrationCorpusService(db)
        first = service.build(user, request)
        assert first["status"] == "partial"
        assert first["slices"]["total"] == 3
        assert first["slices"]["completed"] == 1
        assert first["resume_required"] is True
        run_id = first["run_id"]
        corpus_key = first["corpus_key"]

        second = service.build(user, request)
        assert second["run_id"] == run_id
        assert second["corpus_key"] == corpus_key
        assert second["slices"]["completed"] == 2

        third = service.build(user, request)
        assert third["status"] == "completed"
        assert third["slices"]["completed"] == 3
        assert third["resume_required"] is False
        assert third["evidence_yield"]["forecastable_cases"] == 6
        assert third["evidence_yield"]["outcomes"]["confirmed"] == 3
        assert third["evidence_yield"]["outcomes"]["false"] == 3
        assert third["readiness_distance"]["probability_emission_enabled"] is False
        assert third["critical_semantics"]["thresholds_precommitted_before_scoring"] is True
        assert counters == {"meteo": 3, "rte": 3, "backtest": 3}

        replay = service.build(user, request)
        assert replay["replayed_existing_completed_corpus"] is True
        assert replay["slices_processed_this_call"] == 0
        assert counters == {"meteo": 3, "rte": 3, "backtest": 3}
    finally:
        _cleanup_corpus(db, user.id)
        db.close()


def test_failed_slice_is_retryable_and_never_counted_as_negative_evidence(monkeypatch):
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    attempts = {"meteo": 0}

    def flaky_meteo(self, payload, client=None):  # noqa: ARG001
        attempts["meteo"] += 1
        if attempts["meteo"] == 1:
            raise RuntimeError("archive temporarily unavailable")
        return {"events_promoted": 0, "events_replayed": 0, "errors": []}

    def fake_rte(self, payload, client=None):  # noqa: ARG001
        return {"regional_heat_events_considered": 0, "regions": [], "errors": []}

    def fake_backtest(self, user, payload):  # noqa: ARG001
        return {
            "selected_cases": 0,
            "outcomes": {"confirmed": 0, "partial": 0, "false": 0, "inconclusive": 0, "unresolved": 0},
            "skipped": {},
        }

    monkeypatch.setattr(HorizonHistoricalBackfillService, "backfill_meteofrance_vigilance", flaky_meteo)
    monkeypatch.setattr(HorizonRteCoolingLoadBackfillService, "backfill", fake_rte)
    monkeypatch.setattr(HorizonCoverageAwareHistoricalBacktestFactory, "run", fake_backtest)

    request = HorizonCalibrationCorpusBuildRequest(
        start_at=datetime(2024, 8, 1),
        end_at=datetime(2024, 8, 10),
        slice_days=10,
        outcome_grace_days=7,
        max_slices_per_call=1,
    )
    try:
        service = HorizonCalibrationCorpusService(db)
        failed = service.build(user, request)
        assert failed["status"] == "partial"
        assert failed["slices"]["failed"] == 1
        assert failed["evidence_yield"]["outcomes"]["false"] == 0
        assert failed["critical_semantics"]["failed_slice_is_negative_evidence"] is False

        recovered = service.build(user, request)
        assert recovered["status"] == "completed"
        assert recovered["slices"]["failed"] == 0
        slice_row = db.query(HorizonCalibrationCorpusSlice).filter_by(run_id=recovered["run_id"]).one()
        assert slice_row.attempt_count == 2
        assert attempts["meteo"] == 2
    finally:
        _cleanup_corpus(db, user.id)
        db.close()


def test_corpus_rejects_future_outcome_window():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    try:
        request = HorizonCalibrationCorpusBuildRequest(
            start_at=datetime.utcnow() - timedelta(days=10),
            end_at=datetime.utcnow() - timedelta(days=1),
            outcome_grace_days=7,
        )
        with pytest.raises(ValueError, match="full historical outcome-grace window"):
            HorizonCalibrationCorpusService(db).build(user, request)
    finally:
        db.close()


def test_corpus_routes_are_mounted_on_dedicated_horizon_api():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    external_id = user.external_id
    db.close()

    response = client.get(f"/v1/horizon/corpus/users/{external_id}/runs")
    assert response.status_code == 200, response.text
    assert response.json() == []

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["calibration_corpus_builder_supported"] is True
    assert health.json()["legacy_action_surface_exposed"] is False
