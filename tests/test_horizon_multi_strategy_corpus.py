from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.db import SessionLocal
from app.horizon_collector_models import HorizonCollectorLease
from app.horizon_corpus_models import HorizonCalibrationCorpusRun, HorizonCalibrationCorpusSlice
from app.horizon_corpus_schemas import HorizonCalibrationCorpusBuildRequest
from app.models import User
from app.services.horizon_backfill import HorizonHistoricalBackfillService
from app.services.horizon_backtest_coverage import HorizonCoverageAwareHistoricalBacktestFactory
from app.services.horizon_cold_backfill import HorizonColdHistoricalBackfillService
from app.services.horizon_corpus import HorizonCalibrationCorpusService
from app.services.horizon_corpus_worker import HorizonCorpusWorkerService
from app.services.horizon_rte import HorizonRteCoolingLoadBackfillService
from app.services.horizon_rte_heating import HorizonRteHeatingLoadBackfillService
from app.services.policy import sha256_dict


def _user(db, tag: str) -> User:
    row = User(
        external_id=f"multi-corpus-{tag}",
        country="FR",
        currency="EUR",
        timezone="Europe/Paris",
        preferences={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _cleanup(db, user_id: int):
    run_ids = [row.id for row in db.query(HorizonCalibrationCorpusRun).filter_by(user_id=user_id).all()]
    if run_ids:
        db.query(HorizonCalibrationCorpusSlice).filter(
            HorizonCalibrationCorpusSlice.run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        db.query(HorizonCalibrationCorpusRun).filter(
            HorizonCalibrationCorpusRun.id.in_(run_ids)
        ).delete(synchronize_session=False)
    db.query(HorizonCollectorLease).filter(
        HorizonCollectorLease.collector_key == HorizonCorpusWorkerService.LEASE_KEY
    ).delete(synchronize_session=False)
    db.commit()


def test_heat_and_cold_corpora_have_distinct_identity_and_dispatch(monkeypatch):
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    calls = {"heat_meteo": 0, "heat_rte": 0, "cold_meteo": 0, "cold_rte": 0, "backtest": []}

    def fake_heat_meteo(self, payload, client=None):  # noqa: ARG001
        calls["heat_meteo"] += 1
        return {"events_promoted": 1, "events_replayed": 0, "errors": []}

    def fake_heat_rte(self, payload, client=None):  # noqa: ARG001
        calls["heat_rte"] += 1
        return {
            "regional_heat_events_considered": 1,
            "regions": [{"region_code": "11", "coverage_complete": True}],
            "errors": [],
        }

    def fake_cold_meteo(self, payload, client=None):  # noqa: ARG001
        calls["cold_meteo"] += 1
        assert payload.min_color_id == 3
        return {"events_promoted": 2, "events_replayed": 0, "errors": []}

    def fake_cold_rte(self, payload, client=None):  # noqa: ARG001
        calls["cold_rte"] += 1
        assert payload.minimum_daily_points == 40
        return {
            "regional_cold_events_considered": 2,
            "regions": [{"region_code": "11", "coverage_complete": True}],
            "errors": [],
        }

    def fake_backtest(self, selected_user, payload):  # noqa: ARG001
        calls["backtest"].append(tuple(payload.event_types))
        return {
            "selected_cases": 1,
            "outcomes": {"confirmed": 1, "partial": 0, "false": 0, "inconclusive": 0, "unresolved": 0},
            "skipped": {},
        }

    monkeypatch.setattr(HorizonHistoricalBackfillService, "backfill_meteofrance_vigilance", fake_heat_meteo)
    monkeypatch.setattr(HorizonRteCoolingLoadBackfillService, "backfill", fake_heat_rte)
    monkeypatch.setattr(HorizonColdHistoricalBackfillService, "backfill", fake_cold_meteo)
    monkeypatch.setattr(HorizonRteHeatingLoadBackfillService, "backfill", fake_cold_rte)
    monkeypatch.setattr(HorizonCoverageAwareHistoricalBacktestFactory, "run", fake_backtest)

    common = {
        "start_at": datetime(2024, 1, 1),
        "end_at": datetime(2024, 1, 10),
        "slice_days": 10,
        "outcome_grace_days": 7,
        "max_slices_per_call": 1,
    }
    try:
        service = HorizonCalibrationCorpusService(db)
        heat = service.build(user, HorizonCalibrationCorpusBuildRequest(**common))
        cold = service.build(
            user,
            HorizonCalibrationCorpusBuildRequest(strategy="cold-mf-rte-v1", **common),
        )

        assert heat["status"] == "completed"
        assert cold["status"] == "completed"
        assert heat["strategy"] == "heat-mf-rte-v1"
        assert cold["strategy"] == "cold-mf-rte-v1"
        assert heat["corpus_key"] != cold["corpus_key"]
        assert heat["evidence_yield"]["regional_heat_events_considered"] == 1
        assert cold["evidence_yield"]["regional_cold_events_considered"] == 2
        assert heat["evidence_yield"]["regional_events_considered"] == 1
        assert cold["evidence_yield"]["regional_events_considered"] == 2
        assert heat["critical_semantics"]["strategy_is_part_of_corpus_identity"] is True
        assert cold["critical_semantics"]["cross_strategy_threshold_reuse"] is False
        assert calls == {
            "heat_meteo": 1,
            "heat_rte": 1,
            "cold_meteo": 1,
            "cold_rte": 1,
            "backtest": [("extreme_heat_region",), ("extreme_cold_region",)],
        }

        runs = service.list_runs(user)
        assert {item["strategy"] for item in runs} == {"heat-mf-rte-v1", "cold-mf-rte-v1"}
    finally:
        _cleanup(db, user.id)
        db.close()


def test_corpus_worker_preserves_cold_strategy_when_resuming(monkeypatch):
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    request = HorizonCalibrationCorpusBuildRequest(
        strategy="cold-mf-rte-v1",
        start_at=datetime(2024, 1, 1),
        end_at=datetime(2024, 1, 20),
        slice_days=20,
        outcome_grace_days=7,
        max_slices_per_call=1,
    )
    snapshot = request.model_dump(mode="json", exclude={"max_slices_per_call"})
    snapshot["precommitted_spec"] = {"strategy": "cold-mf-rte-v1", "fixture": True}
    run = HorizonCalibrationCorpusRun(
        corpus_key=sha256_dict({"cold-worker": tag}),
        user_id=user.id,
        engine_version="fixture",
        requested_start_at=datetime(2024, 1, 1),
        requested_end_at=datetime(2024, 1, 20),
        slice_days=20,
        outcome_grace_days=7,
        request_snapshot=snapshot,
        summary_snapshot={},
        status="partial",
        created_at=datetime.utcnow() - timedelta(days=1),
        updated_at=datetime.utcnow() - timedelta(hours=12),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    seen = {}

    def fake_build(self, selected_user, resumed_request):  # noqa: ARG001
        seen["user_id"] = selected_user.id
        seen["strategy"] = resumed_request.strategy
        seen["max_slices_per_call"] = resumed_request.max_slices_per_call
        seen["minimum_daily_points"] = resumed_request.rte_minimum_daily_points
        return {
            "status": "partial",
            "slices_processed_this_call": 1,
            "resume_required": True,
            "readiness_distance": {
                "binary_labels_missing": 49,
                "distinct_events_missing": 9,
                "probability_emission_enabled": False,
            },
        }

    monkeypatch.setattr(HorizonCalibrationCorpusService, "build", fake_build)
    try:
        result = HorizonCorpusWorkerService(db).run_once(
            owner_id="cold-corpus-worker",
            lease_seconds=3600,
            max_runs=1,
            slices_per_run=1,
        )
        assert result["status"] == "completed"
        assert result["runs_considered"] == 1
        assert seen == {
            "user_id": user.id,
            "strategy": "cold-mf-rte-v1",
            "max_slices_per_call": 1,
            "minimum_daily_points": 40,
        }
    finally:
        _cleanup(db, user.id)
        db.close()


def test_legacy_heat_snapshot_without_strategy_remains_resumable(monkeypatch):
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = _user(db, tag)
    snapshot = {
        "start_at": "2024-06-01T00:00:00",
        "end_at": "2024-07-01T00:00:00",
        "slice_days": 30,
        "outcome_grace_days": 7,
        "departments": [],
        "meteo_min_color_id": 3,
        "meteo_max_snapshots_per_slice": 500,
        "meteo_merge_gap_hours": 24,
        "rte_baseline_lookback_days": 28,
        "rte_minimum_lift_ratio": 0.03,
        "rte_minimum_afternoon_points": 12,
        "rte_max_records_per_slice": 50000,
        "backtest_max_events": 500,
        "backtest_max_cases": 3000,
        "precommitted_spec": {"fixture": "legacy-heat"},
    }
    run = HorizonCalibrationCorpusRun(
        corpus_key=sha256_dict({"legacy-heat": tag}),
        user_id=user.id,
        engine_version="horizon-calibration-corpus-builder-v0.1",
        requested_start_at=datetime(2024, 6, 1),
        requested_end_at=datetime(2024, 7, 1),
        slice_days=30,
        outcome_grace_days=7,
        request_snapshot=snapshot,
        summary_snapshot={},
        status="partial",
        created_at=datetime.utcnow() - timedelta(days=1),
        updated_at=datetime.utcnow() - timedelta(hours=12),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    seen = {}

    def fake_build(self, selected_user, resumed_request):  # noqa: ARG001
        seen["strategy"] = resumed_request.strategy
        return {
            "status": "partial",
            "slices_processed_this_call": 1,
            "resume_required": True,
            "readiness_distance": {},
        }

    monkeypatch.setattr(HorizonCalibrationCorpusService, "build", fake_build)
    try:
        HorizonCorpusWorkerService(db).run_once(
            owner_id="legacy-corpus-worker",
            lease_seconds=3600,
            max_runs=1,
            slices_per_run=1,
        )
        assert seen["strategy"] == "heat-mf-rte-v1"
    finally:
        _cleanup(db, user.id)
        db.close()
