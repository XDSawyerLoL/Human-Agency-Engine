from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.db import SessionLocal
from app.horizon_collector_models import HorizonCollectorLease
from app.horizon_corpus_models import HorizonCalibrationCorpusRun, HorizonCalibrationCorpusSlice
from app.models import User
from app.services.horizon_corpus import HorizonCalibrationCorpusService
from app.services.horizon_corpus_worker import HorizonCorpusWorkerService
from app.services.policy import sha256_dict


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


def _user_and_run(db):
    tag = uuid4().hex[:10]
    user = User(
        external_id=f"corpus-worker-{tag}",
        country="FR",
        currency="EUR",
        timezone="Europe/Paris",
        preferences={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request_snapshot = {
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
        "precommitted_spec": {"fixture": True},
    }
    run = HorizonCalibrationCorpusRun(
        corpus_key=sha256_dict({"fixture": tag}),
        user_id=user.id,
        engine_version="fixture",
        requested_start_at=datetime(2024, 6, 1),
        requested_end_at=datetime(2024, 7, 1),
        slice_days=30,
        outcome_grace_days=7,
        request_snapshot=request_snapshot,
        summary_snapshot={},
        status="partial",
        created_at=datetime.utcnow() - timedelta(days=1),
        updated_at=datetime.utcnow() - timedelta(hours=12),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return user, run


def test_corpus_worker_resumes_pending_run_with_bounded_slice_count(monkeypatch):
    db = SessionLocal()
    user, run = _user_and_run(db)
    seen = {}

    def fake_build(self, selected_user, request):  # noqa: ARG001
        seen["user_id"] = selected_user.id
        seen["max_slices_per_call"] = request.max_slices_per_call
        return {
            "status": "partial",
            "slices_processed_this_call": 1,
            "resume_required": True,
            "readiness_distance": {
                "binary_labels_missing": 42,
                "distinct_events_missing": 8,
                "probability_emission_enabled": False,
            },
        }

    monkeypatch.setattr(HorizonCalibrationCorpusService, "build", fake_build)
    try:
        result = HorizonCorpusWorkerService(db).run_once(
            owner_id="corpus-worker-a",
            lease_seconds=3600,
            max_runs=1,
            slices_per_run=1,
        )
        assert result["status"] == "completed"
        assert result["runs_considered"] == 1
        assert result["results"][0]["run_id"] == run.id
        assert result["results"][0]["slices_processed"] == 1
        assert seen == {"user_id": user.id, "max_slices_per_call": 1}
        assert result["critical_semantics"]["historical_work_is_rate_separated_from_live_collection"] is True
        assert result["critical_semantics"]["numeric_probabilities_enabled"] is False
    finally:
        _cleanup(db, user.id)
        db.close()


def test_corpus_worker_lease_blocks_parallel_owner(monkeypatch):
    db1 = SessionLocal()
    db2 = SessionLocal()
    user, _ = _user_and_run(db1)
    try:
        first = HorizonCorpusWorkerService(db1).acquire_lease("leader-a", lease_seconds=3600)
        assert first["acquired"] is True

        result = HorizonCorpusWorkerService(db2).run_once(owner_id="leader-b", lease_seconds=3600)
        assert result["status"] == "standby"
        assert result["leader"]["owner_id"] == "leader-a"
        assert result["numeric_probabilities_enabled"] is False
    finally:
        db2.close()
        _cleanup(db1, user.id)
        db1.close()


def test_corpus_worker_is_idle_without_pending_corpus():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    user = User(
        external_id=f"corpus-worker-idle-{tag}",
        country="FR",
        currency="EUR",
        timezone="Europe/Paris",
        preferences={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    try:
        _cleanup(db, user.id)
        result = HorizonCorpusWorkerService(db).run_once(owner_id="idle-worker", lease_seconds=3600)
        assert result["status"] == "idle"
        assert result["pending_runs"] == 0
        assert result["numeric_probabilities_enabled"] is False
    finally:
        _cleanup(db, user.id)
        db.close()
