from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent
from app.horizon_provisional_models import HorizonProvisionalForecast, HorizonProvisionalResolution
from app.horizon_provisional_schemas import HorizonProvisionalReconcileRequest, HorizonProvisionalRefreshRequest
from app.horizon_source_models import HorizonEventCandidate
from app.main import app
from app.services.horizon_provisional import HorizonProvisionalService
from app.services.policy import sha256_dict

api = TestClient(app)


def _candidate(db, *, event_type: str = "supply_disruption") -> HorizonEventCandidate:
    suffix = uuid4().hex[:10]
    now = datetime.utcnow().replace(microsecond=0)
    row = HorizonEventCandidate(
        candidate_key=sha256_dict({"fixture": suffix}),
        event_type=event_type,
        title="Unconfirmed emerging disruption",
        geography=[],
        corroborating_observation_ids=[],
        source_classes=["news_global"],
        normalized_facts={
            "fact_status": "unconfirmed_emerging_event",
            "candidate_not_fact": True,
            "raw_claims_verified": False,
            "geography_status": "unknown",
        },
        normalizer_version="fixture-v1",
        corroboration_score=0.46,
        promotion_status="candidate",
        promoted_event_id=None,
        first_observed_at=now - timedelta(minutes=30),
        last_observed_at=now - timedelta(minutes=15),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_unconfirmed_candidate_starts_internal_provisional_forecast_without_notification_or_fake_dates():
    db = SessionLocal()
    try:
        candidate = _candidate(db)
        first = HorizonProvisionalService(db).refresh(
            HorizonProvisionalRefreshRequest(max_candidates=100)
        )
        item = next(row for row in first["forecasts"] if row["candidate_id"] == candidate.id)
        assert item["fact_status"] == "unconfirmed_emerging_event"
        assert item["geography_status"] == "unknown"
        assert item["user_surface_allowed"] is False
        assert item["probability_basis"] == "not_calibrated"
        assert first["user_notification_performed"] is False
        assert first["external_action_executed"] is False

        forecast = db.query(HorizonProvisionalForecast).filter(
            HorizonProvisionalForecast.id == item["forecast_id"]
        ).one()
        assert forecast.interpretation["candidate_is_confirmed_fact"] is False
        assert forecast.interpretation["provisional_score_is_probability"] is False
        assert forecast.interpretation["absolute_onset_window_available"] is False
        assert forecast.interpretation["user_notification_allowed"] is False

        second = HorizonProvisionalService(db).refresh(
            HorizonProvisionalRefreshRequest(max_candidates=100)
        )
        replay = next(row for row in second["forecasts"] if row["candidate_id"] == candidate.id)
        assert replay["forecast_id"] == forecast.id
        assert second["forecasts_reused"] >= 1
    finally:
        db.close()


def test_promotion_resolves_corroboration_lead_but_never_labels_it_predictive_lead():
    db = SessionLocal()
    try:
        candidate = _candidate(db)
        result = HorizonProvisionalService(db).refresh(
            HorizonProvisionalRefreshRequest(max_candidates=100)
        )
        forecast_id = next(
            row["forecast_id"] for row in result["forecasts"] if row["candidate_id"] == candidate.id
        )
        forecast = db.query(HorizonProvisionalForecast).filter_by(id=forecast_id).one()

        event = HorizonGlobalEvent(
            event_key=f"confirmed-{uuid4().hex[:12]}",
            event_type=candidate.event_type,
            title="Confirmed disruption",
            summary="Independent evidence confirmed the event",
            geography=["FR"],
            source="official-fixture",
            source_url="",
            source_reliability=0.97,
            raw_facts={"corroboration": {"official_primary_present": True}},
            occurred_at=forecast.as_of,
            first_observed_at=candidate.first_observed_at,
            status="active",
            created_at=forecast.as_of + timedelta(hours=2),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        candidate.promoted_event_id = event.id
        candidate.promotion_status = "promoted"
        db.commit()

        reconciled = HorizonProvisionalService(db).reconcile(
            HorizonProvisionalReconcileRequest(max_forecasts=500)
        )
        row = next(item for item in reconciled["resolutions"] if item["forecast_id"] == forecast.id)
        assert row["promoted_event_id"] == event.id
        assert row["corroboration_lead_time_hours"] == 2.0
        assert row["predictive_lead_time_hours"] is None
        assert reconciled["corroboration_lead_time_is_predictive_lead_time"] is False

        resolution = db.query(HorizonProvisionalResolution).filter_by(forecast_id=forecast.id).one()
        assert resolution.evidence["corroboration_lead_time_is_predictive_lead_time"] is False
        assert resolution.evidence["predictive_lead_requires_later_materialization_label"] is True

        replay = HorizonProvisionalService(db).reconcile(
            HorizonProvisionalReconcileRequest(max_forecasts=500)
        )
        assert all(item["forecast_id"] != forecast.id for item in replay["resolutions"])
    finally:
        db.close()


def test_provisional_routes_are_mounted(monkeypatch):
    monkeypatch.setattr(
        HorizonProvisionalService,
        "refresh",
        lambda self, payload: {
            "candidates_scanned": 0,
            "forecasts_created": 0,
            "forecasts_reused": 0,
            "candidates_without_pattern": 0,
            "forecasts": [],
            "provisional_forecasts_are_confirmed_facts": False,
            "user_notification_performed": False,
            "external_action_executed": False,
        },
    )
    monkeypatch.setattr(
        HorizonProvisionalService,
        "reconcile",
        lambda self, payload: {
            "forecasts_scanned": 0,
            "resolved_by_corroboration": 0,
            "still_unconfirmed": 0,
            "resolutions": [],
            "corroboration_lead_time_is_predictive_lead_time": False,
        },
    )
    refresh = api.post("/v1/horizon/provisional-forecasts/refresh", json={"max_candidates": 10})
    reconcile = api.post("/v1/horizon/provisional-forecasts/reconcile", json={"max_forecasts": 10})
    assert refresh.status_code == 200, refresh.text
    assert reconcile.status_code == 200, reconcile.text
    assert refresh.json()["user_notification_performed"] is False
    assert reconcile.json()["corroboration_lead_time_is_predictive_lead_time"] is False
