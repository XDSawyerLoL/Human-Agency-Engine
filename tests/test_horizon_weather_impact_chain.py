from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.horizon_provisional_models import HorizonProvisionalForecast, HorizonProvisionalResolution
from app.horizon_source_models import HorizonEventCandidate
from app.horizon_weather_chain_models import HorizonWeatherImpactChain
from app.main import app
from app.services.horizon_provisional import HorizonProvisionalService
from app.horizon_provisional_schemas import HorizonProvisionalRefreshRequest
from app.services.horizon_weather_chain import HorizonWeatherChainService


client = TestClient(app)


def _windy_candidate(db, *, department: str, first_observed_at: datetime, tag: str) -> HorizonEventCandidate:
    candidate = HorizonEventCandidate(
        candidate_key=f"windy-chain-{tag}",
        event_type="extreme_heat",
        title="Windy multi-model extreme-heat watch",
        geography=["FR", department],
        corroborating_observation_ids=[],
        source_classes=["model_forecast"],
        normalized_facts={
            "forecast_only": True,
            "provider": "windy",
            "geography_status": "known",
            "forecast_target_window": {
                "start": (first_observed_at + timedelta(hours=12)).isoformat(),
                "end": (first_observed_at + timedelta(hours=24)).isoformat(),
            },
            "heat_consensus": {
                "supporting_models": ["aromeFrance", "iconEu", "gfs"],
                "supporting_model_count": 3,
            },
        },
        normalizer_version="horizon-windy-weather-dynamics-v0.1",
        corroboration_score=0.7,
        promotion_status="candidate",
        first_observed_at=first_observed_at,
        last_observed_at=first_observed_at,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    HorizonProvisionalService(db).refresh(HorizonProvisionalRefreshRequest(max_candidates=1000))
    # The fixture represents a forecast created immediately after the Windy snapshot,
    # even though the test itself is replaying a synthetic timestamp.
    forecasts = db.query(HorizonProvisionalForecast).filter(
        HorizonProvisionalForecast.candidate_id == candidate.id
    ).all()
    for forecast in forecasts:
        forecast.as_of = first_observed_at + timedelta(minutes=1)
    db.commit()
    return candidate


def _official_event(
    db,
    *,
    department: str,
    first_observed_at: datetime,
    validity_start: datetime,
    validity_end: datetime,
    tag: str,
) -> HorizonGlobalEvent:
    event = HorizonGlobalEvent(
        event_key=f"official-heat-{tag}",
        event_type="extreme_heat",
        title=f"Vigilance canicule {department}",
        summary="Synthetic official-primary confirmation fixture.",
        geography=["FR"],
        source="meteofrance-vigilance",
        source_url="https://vigilance.meteofrance.fr/fr",
        source_reliability=0.97,
        raw_facts={
            "normalized_facts": {
                "domain_id": department,
                "domain_kind": "department",
                "phenomenon_id": "6",
                "period": {
                    "begin_validity_time": validity_start.isoformat(),
                    "end_validity_time": validity_end.isoformat(),
                },
            }
        },
        occurred_at=first_observed_at,
        first_observed_at=first_observed_at,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_windy_confirmation_requires_same_department_and_overlapping_validity_window():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    start = datetime(2026, 8, 1, 0, 0, 0)
    try:
        candidate = _windy_candidate(db, department="75", first_observed_at=start, tag=tag)
        _official_event(
            db,
            department="92",
            first_observed_at=start + timedelta(hours=4),
            validity_start=start + timedelta(hours=12),
            validity_end=start + timedelta(hours=24),
            tag=f"wrong-geo-{tag}",
        )
        _official_event(
            db,
            department="75",
            first_observed_at=start + timedelta(hours=5),
            validity_start=start + timedelta(hours=30),
            validity_end=start + timedelta(hours=40),
            tag=f"wrong-time-{tag}",
        )

        first = HorizonWeatherChainService(db).match_official_confirmations(max_forecasts=5000)
        assert first["windy_candidates_matched"] == 0
        forecasts = db.query(HorizonProvisionalForecast).filter(
            HorizonProvisionalForecast.candidate_id == candidate.id
        ).all()
        assert forecasts
        assert not db.query(HorizonProvisionalResolution).filter(
            HorizonProvisionalResolution.forecast_id.in_([row.id for row in forecasts])
        ).all()

        matching = _official_event(
            db,
            department="75",
            first_observed_at=start + timedelta(hours=6),
            validity_start=start + timedelta(hours=10),
            validity_end=start + timedelta(hours=26),
            tag=f"match-{tag}",
        )
        second = HorizonWeatherChainService(db).match_official_confirmations(max_forecasts=5000)
        assert second["windy_candidates_matched"] == 1
        assert second["provisional_forecasts_skipped_as_hindsight"] == 0
        match = next(item for item in second["matches"] if item["candidate_id"] == candidate.id)
        assert match["confirmed_event_id"] == matching.id
        assert match["windy_to_official_lead_hours"] == 6.0

        db.refresh(candidate)
        assert candidate.promoted_event_id is None
        assert candidate.promotion_status == "candidate"
        own_resolutions = (
            db.query(HorizonProvisionalResolution)
            .join(HorizonProvisionalForecast, HorizonProvisionalForecast.id == HorizonProvisionalResolution.forecast_id)
            .filter(HorizonProvisionalForecast.candidate_id == candidate.id)
            .all()
        )
        assert own_resolutions
        assert all(row.resolution_type == "matched_external_official_confirmation" for row in own_resolutions)
        assert all(row.evidence["windy_candidate_was_promoted"] is False for row in own_resolutions)
        assert all(row.evidence["forecast_existed_before_confirmation"] is True for row in own_resolutions)
    finally:
        db.close()


def test_forecast_created_after_official_confirmation_cannot_receive_windy_lead_credit():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    start = datetime(2026, 8, 3, 0, 0, 0)
    try:
        candidate = _windy_candidate(db, department="75", first_observed_at=start, tag=f"hindsight-{tag}")
        official = _official_event(
            db,
            department="75",
            first_observed_at=start + timedelta(hours=6),
            validity_start=start + timedelta(hours=10),
            validity_end=start + timedelta(hours=26),
            tag=f"hindsight-{tag}",
        )
        forecasts = db.query(HorizonProvisionalForecast).filter(
            HorizonProvisionalForecast.candidate_id == candidate.id
        ).all()
        for forecast in forecasts:
            forecast.as_of = official.first_observed_at + timedelta(minutes=1)
        db.commit()

        result = HorizonWeatherChainService(db).match_official_confirmations(max_forecasts=5000)
        assert result["windy_candidates_matched"] == 0
        assert result["provisional_forecasts_skipped_as_hindsight"] >= len(forecasts)
        own = (
            db.query(HorizonProvisionalResolution)
            .join(HorizonProvisionalForecast, HorizonProvisionalForecast.id == HorizonProvisionalResolution.forecast_id)
            .filter(HorizonProvisionalForecast.candidate_id == candidate.id)
            .all()
        )
        assert own == []
    finally:
        db.close()


def test_weather_impact_chain_preserves_distinct_confirmation_and_behavior_lead_times():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    start = datetime(2026, 8, 2, 0, 0, 0)
    try:
        candidate = _windy_candidate(db, department="75", first_observed_at=start, tag=f"chain-{tag}")
        official = _official_event(
            db,
            department="75",
            first_observed_at=start + timedelta(hours=6),
            validity_start=start + timedelta(hours=10),
            validity_end=start + timedelta(hours=26),
            tag=f"chain-{tag}",
        )
        confirmation = HorizonWeatherChainService(db).match_official_confirmations(max_forecasts=5000)
        assert confirmation["windy_candidates_matched"] == 1

        regional = HorizonGlobalEvent(
            event_key=f"regional-chain-{tag}",
            event_type="extreme_heat_region",
            title="Regional heat state",
            summary="Derived regional state fixture.",
            geography=["FR", "REGION:11"],
            source="meteofrance-vigilance-archive",
            source_url="https://vigilance.meteofrance.fr/fr",
            source_reliability=0.97,
            raw_facts={
                "derived_fact": True,
                "member_event_ids": [official.id, official.id + 1000000],
                "departments": ["75", "92"],
                "region_code": "11",
            },
            occurred_at=start + timedelta(hours=8),
            first_observed_at=start + timedelta(hours=8),
            status="active",
        )
        db.add(regional)
        db.commit()
        db.refresh(regional)

        signal = HorizonSocialSignal(
            event_id=regional.id,
            signal_key=f"rte-chain-{tag}",
            signal_type="cooling_load_pressure",
            source="rte-eco2mix-regional-cons-def",
            geography=["FR", "REGION:11"],
            value=1100,
            baseline=1000,
            normalized_score=2.0,
            direction="up",
            reliability=0.94,
            evidence={"cooling_causality_proven": False},
            observed_at=start + timedelta(hours=18),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)

        impacts = HorizonWeatherChainService(db).refresh_impact_chains(max_chains=5000)
        assert impacts["impact_chains_created"] == 1
        own = db.query(HorizonWeatherImpactChain).filter(
            HorizonWeatherImpactChain.windy_candidate_id == candidate.id
        ).one()
        assert own.confirmed_event_id == official.id
        assert own.regional_event_id == regional.id
        assert own.outcome_signal_id == signal.id
        assert own.windy_to_official_lead_hours == 6.0
        assert own.official_to_behavior_lag_hours == 12.0
        assert own.windy_to_behavior_lead_hours == 18.0
        assert own.evidence["chain_is_causal_proof"] is False
        assert own.evidence["heat_causality_proven_by_rte_load"] is False

        replay = HorizonWeatherChainService(db).refresh_impact_chains(max_chains=5000)
        assert replay["impact_chains_created"] == 0
        assert db.query(HorizonWeatherImpactChain).filter(
            HorizonWeatherImpactChain.windy_candidate_id == candidate.id
        ).count() == 1
    finally:
        db.close()


def test_weather_chain_routes_are_mounted():
    response = client.get("/v1/horizon/weather-chains")
    assert response.status_code == 200, response.text
    reconcile = client.post(
        "/v1/horizon/weather-chains/reconcile",
        json={"max_forecasts": 100, "max_chains": 100},
    )
    assert reconcile.status_code == 200, reconcile.text
    assert reconcile.json()["engine"] == "horizon-windy-confirmation-impact-chain-v0.1"
