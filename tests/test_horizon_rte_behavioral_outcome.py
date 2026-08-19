from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_backfill_models import HorizonHistoricalCoverageInterval
from app.horizon_backfill_schemas import HorizonRteCoolingLoadBackfillRequest
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.main import app
from app.services.horizon_heat_regions import HorizonRegionalHeatService
from app.services.horizon_response_library import HorizonResponseLibraryService
from app.services.horizon_rte import HorizonRteCoolingLoadBackfillService, RTE_REGIONAL_ENDPOINT


client = TestClient(app)


def _department_heat_event(db, key: str, department: str, first_observed_at: datetime) -> HorizonGlobalEvent:
    row = HorizonGlobalEvent(
        event_key=key,
        event_type="extreme_heat",
        title=f"Synthetic heat {department}",
        summary="Synthetic official heat event for regional-outcome validation.",
        geography=["FR", department],
        source="meteofrance-vigilance-archive",
        source_url="https://vigilance.meteofrance.fr/fr",
        source_reliability=0.97,
        raw_facts={
            "normalized_facts": {
                "department": department,
                "episode_start": "2023-07-01T10:00:00Z",
                "episode_end": "2023-07-02T20:00:00Z",
                "max_color_id": 3,
            }
        },
        occurred_at=first_observed_at,
        first_observed_at=first_observed_at,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _rte_fixture_records() -> list[dict]:
    rows = []
    day = datetime(2023, 5, 27, tzinfo=timezone.utc)
    end = datetime(2023, 7, 5, tzinfo=timezone.utc)
    while day.date() <= end.date():
        target = day.date() >= datetime(2023, 7, 1).date()
        value = 1100 if target else 1000
        # In July, 10:00..17:30 UTC maps to 12:00..19:30 Europe/Paris.
        for index in range(16):
            at = day.replace(hour=10, minute=0) + timedelta(minutes=30 * index)
            rows.append(
                {
                    "code_insee_region": "11",
                    "libelle_region": "Île-de-France",
                    "date_heure": at.isoformat().replace("+00:00", "Z"),
                    "consommation": value,
                    "nature": "Données définitives",
                }
            )
        day += timedelta(days=1)
    return rows


def test_regional_heat_state_requires_two_departments_and_uses_second_observation_time():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    try:
        first = _department_heat_event(
            db,
            f"regional-first-{tag}",
            "75",
            datetime(2023, 7, 1, 8, 0, 0),
        )
        result_one = HorizonRegionalHeatService(db).aggregate(
            start_at=datetime(2023, 7, 1),
            end_at=datetime(2023, 7, 3),
        )
        assert result_one["regional_events_created"] == 0

        second = _department_heat_event(
            db,
            f"regional-second-{tag}",
            "92",
            datetime(2023, 7, 1, 9, 0, 0),
        )
        result_two = HorizonRegionalHeatService(db).aggregate(
            start_at=datetime(2023, 7, 1),
            end_at=datetime(2023, 7, 3),
        )
        assert result_two["regional_events_created"] >= 1
        regional = db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id.in_(result_two["regional_event_ids"])
        ).first()
        assert regional is not None
        assert regional.event_type == "extreme_heat_region"
        assert regional.geography == ["FR", "REGION:11"]
        assert regional.first_observed_at == second.first_observed_at
        assert regional.occurred_at == second.first_observed_at
        assert set(regional.raw_facts["departments"]) >= {"75", "92"}
        assert first.id in regional.raw_facts["member_event_ids"]
        assert second.id in regional.raw_facts["member_event_ids"]
    finally:
        db.close()


def test_rte_regional_load_becomes_covered_behavioral_outcome_and_backtest_success():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    records = _rte_fixture_records()
    try:
        _department_heat_event(
            db,
            f"rte-first-{tag}",
            "75",
            datetime(2023, 7, 1, 8, 0, 0),
        )
        _department_heat_event(
            db,
            f"rte-second-{tag}",
            "92",
            datetime(2023, 7, 1, 9, 0, 0),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).startswith(RTE_REGIONAL_ENDPOINT)
            offset = int(request.url.params.get("offset", "0"))
            limit = int(request.url.params.get("limit", "100"))
            page = records[offset : offset + limit]
            return httpx.Response(200, json={"results": page, "total_count": len(records)}, request=request)

        mock = httpx.Client(transport=httpx.MockTransport(handler))
        service = HorizonRteCoolingLoadBackfillService(db)
        request = HorizonRteCoolingLoadBackfillRequest(
            start_at=datetime(2023, 7, 1, 0, 0, 0),
            end_at=datetime(2023, 7, 5, 23, 59, 59),
            baseline_lookback_days=28,
            minimum_lift_ratio=0.03,
            minimum_afternoon_points=12,
            max_records=5000,
        )
        result = service.backfill(request, client=mock)
        mock.close()

        assert result["regional_heat_events_considered"] >= 1
        assert "11" in result["region_codes"]
        assert result["cooling_load_signal_links_created_or_reused"] >= 1
        assert result["critical_semantics"]["rte_load_proves_air_conditioning_causality"] is False
        assert result["critical_semantics"]["negative_labels_require_complete_signal_coverage"] is True
        region_result = next(item for item in result["regions"] if item["region_code"] == "11")
        assert region_result["coverage_complete"] is True

        signals = db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.source == "rte-eco2mix-regional-cons-def",
            HorizonSocialSignal.signal_type == "cooling_load_pressure",
        ).all()
        matching = [row for row in signals if row.signal_key.startswith("rte-cooling-load:")]
        assert matching
        assert all(row.reliability == 0.94 for row in matching)
        assert all(row.normalized_score >= 1.0 for row in matching)
        assert all(row.evidence["cooling_causality_proven"] is False for row in matching)

        coverage = db.query(HorizonHistoricalCoverageInterval).filter(
            HorizonHistoricalCoverageInterval.id == region_result["coverage_interval_id"]
        ).one()
        assert coverage.coverage_kind == "signal"
        assert coverage.signal_types == ["cooling_load_pressure"]
        assert coverage.event_types == ["extreme_heat_region"]
        assert coverage.geography == ["FR", "REGION:11"]
        assert coverage.completeness == "complete"

        HorizonResponseLibraryService(db).sync_builtins()
        uid = f"rte-backtest-{tag}"
        user_response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
        assert user_response.status_code == 200, user_response.text
        backtest = client.post(
            f"/v1/horizon/backtests/users/{uid}/run",
            json={
                "start_at": "2023-07-01T00:00:00Z",
                "end_at": "2023-07-01T23:59:59Z",
                "evaluation_as_of": "2023-07-06T12:00:00Z",
                "event_types": ["extreme_heat_region"],
                "max_events": 50,
                "max_cases": 50,
            },
        )
        assert backtest.status_code == 200, backtest.text
        body = backtest.json()
        assert body["selected_cases"] >= 1
        assert body["outcomes"]["confirmed"] >= 1
        assert body["critical_semantics"]["absence_of_signal_without_complete_coverage_counts_as_failure"] is False
        assert body["calibration_after_run"]["probability_calibration_enabled"] is False
    finally:
        db.close()
