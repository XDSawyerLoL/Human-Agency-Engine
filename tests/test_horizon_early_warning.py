from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_schemas import HorizonEventCreate, HorizonPatternCreate, HorizonSignalCreate
from app.horizon_warning_models import HorizonEarlyWarningEpisode, HorizonEarlyWarningSnapshot
from app.horizon_warning_schemas import HorizonWarningProjectRequest
from app.main import app
from app.services.horizon import HorizonService
from app.services.horizon_warning import HorizonWarningService

api = TestClient(app)


def _fixture():
    db = SessionLocal()
    now = datetime.utcnow().replace(microsecond=0)
    suffix = uuid4().hex[:10]
    horizon = HorizonService(db)
    event = horizon.create_event(
        HorizonEventCreate(
            event_key=f"warning-event-{suffix}",
            event_type="test_warning_event",
            title="Test warning event",
            summary="Synthetic event for deterministic convergence testing",
            geography=["FR"],
            source="official-fixture",
            source_reliability=0.95,
            raw_facts={},
            occurred_at=now - timedelta(hours=4),
            first_observed_at=now - timedelta(hours=4),
        )
    )
    pattern = horizon.create_pattern(
        HorizonPatternCreate(
            pattern_key=f"warning-pattern-{suffix}",
            name="Attention then material pressure",
            event_types=["test_warning_event"],
            required_signal_types=["media_attention", "stock_availability"],
            predicted_response="Attention may precede material availability pressure",
            mechanism_chain=["attention rises", "material pressure"],
            expected_lag_hours_low=6,
            expected_lag_hours_high=48,
            confidence=0.62,
            provenance={
                "stage_signal_types": {
                    "0": ["media_attention"],
                    "1": ["stock_availability"],
                }
            },
            knowledge_available_at=now - timedelta(days=1),
        )
    )
    first = horizon.add_signal(
        event.id,
        HorizonSignalCreate(
            signal_key=f"warning-media-{suffix}",
            signal_type="media_attention",
            source="gdelt-timeline",
            geography=["FR"],
            value=4.0,
            baseline=1.0,
            normalized_score=1.4,
            direction="up",
            reliability=0.72,
            evidence={"does_not_measure": ["purchase_behavior"]},
            observed_at=now - timedelta(hours=2),
        ),
    )
    return db, now, suffix, event, pattern, first


def test_early_warning_backtest_cannot_see_future_signal_and_converges_only_across_independent_families():
    db, now, suffix, event, pattern, _ = _fixture()
    try:
        early = HorizonWarningService(db).project(
            HorizonWarningProjectRequest(
                event_id=event.id,
                pattern_id=pattern.id,
                mode="backtest",
                as_of=now - timedelta(hours=1),
                recency_hours=24,
            )
        )
        assert early.family_count == 1
        assert early.source_count == 1
        assert early.signal_families == ["attention"]
        assert early.convergence_band == "emerging"
        assert early.interpretation["convergence_score_is_probability"] is False
        assert early.interpretation["formal_probability_enabled"] is False

        HorizonService(db).add_signal(
            event.id,
            HorizonSignalCreate(
                signal_key=f"warning-stock-{suffix}",
                signal_type="stock_availability",
                source="official-material-feed",
                geography=["FR"],
                value=0.60,
                baseline=1.0,
                normalized_score=0.80,
                direction="down",
                reliability=0.96,
                evidence={"does_not_measure": ["panic_buying", "cause_of_shortage"]},
                observed_at=now - timedelta(minutes=30),
            ),
        )

        later = HorizonWarningService(db).project(
            HorizonWarningProjectRequest(
                event_id=event.id,
                pattern_id=pattern.id,
                mode="backtest",
                as_of=now,
                recency_hours=24,
            )
        )
        assert later.episode_id == early.episode_id
        assert later.id != early.id
        assert later.family_count == 2
        assert later.source_count == 2
        assert later.signal_families == ["attention", "material_availability"]
        assert later.convergence_band == "converging"
        assert later.interpretation["probability_basis"] == "not_calibrated"
        assert later.interpretation["lead_hours_are_measured_predictive_lead_time"] is False

        replay = HorizonWarningService(db).project(
            HorizonWarningProjectRequest(
                event_id=event.id,
                pattern_id=pattern.id,
                mode="backtest",
                as_of=now,
                recency_hours=24,
            )
        )
        assert replay.id == later.id
        assert db.query(HorizonEarlyWarningEpisode).filter_by(id=later.episode_id).count() == 1
        assert db.query(HorizonEarlyWarningSnapshot).filter_by(episode_id=later.episode_id).count() == 2
    finally:
        db.close()


def test_two_signal_types_from_same_source_do_not_claim_independent_convergence():
    db, now, suffix, event, pattern, _ = _fixture()
    try:
        HorizonService(db).add_signal(
            event.id,
            HorizonSignalCreate(
                signal_key=f"warning-stock-same-source-{suffix}",
                signal_type="stock_availability",
                source="gdelt-timeline",
                geography=["FR"],
                value=0.65,
                baseline=1.0,
                normalized_score=0.7,
                direction="down",
                reliability=0.7,
                evidence={},
                observed_at=now - timedelta(minutes=20),
            ),
        )
        snapshot = HorizonWarningService(db).project(
            HorizonWarningProjectRequest(
                event_id=event.id,
                pattern_id=pattern.id,
                mode="backtest",
                as_of=now,
                recency_hours=24,
            )
        )
        assert snapshot.family_count == 2
        assert snapshot.source_count == 1
        assert snapshot.convergence_band == "emerging"
    finally:
        db.close()


def test_early_warning_route_is_mounted():
    db, now, _, event, pattern, _ = _fixture()
    try:
        response = api.post(
            "/v1/horizon/warnings/project",
            json={
                "event_id": event.id,
                "pattern_id": pattern.id,
                "mode": "backtest",
                "as_of": (now - timedelta(hours=1)).isoformat(),
                "recency_hours": 24,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["convergence_band"] == "emerging"
        assert body["interpretation"]["convergence_score_is_probability"] is False
    finally:
        db.close()
