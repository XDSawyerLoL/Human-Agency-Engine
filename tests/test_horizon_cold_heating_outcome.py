from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_backfill_models import HorizonHistoricalCoverageInterval
from app.horizon_cold_schemas import HorizonRteHeatingLoadBackfillRequest
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.horizon_api import app as horizon_app
from app.main import app
from app.services.horizon_cold_backfill import extract_cold_intervals
from app.services.horizon_cold_regions import HorizonRegionalColdService
from app.services.horizon_rte import RTE_REGIONAL_ENDPOINT
from app.services.horizon_rte_heating import HorizonRteHeatingLoadBackfillService


client = TestClient(app)
horizon_client = TestClient(horizon_app)
PARIS = ZoneInfo("Europe/Paris")


def _department_cold_event(db, key: str, department: str, first_observed_at: datetime) -> HorizonGlobalEvent:
    row = HorizonGlobalEvent(
        event_key=key,
        event_type="extreme_cold",
        title=f"Synthetic cold {department}",
        summary="Synthetic official cold event for regional heating-outcome validation.",
        geography=["FR", department],
        source="meteofrance-vigilance-archive",
        source_url="https://vigilance.meteofrance.fr/fr",
        source_reliability=0.97,
        raw_facts={
            "normalized_facts": {
                "department": department,
                "phenomenon_id": "7",
                "episode_start": "2023-01-01T06:00:00Z",
                "episode_end": "2023-01-02T22:00:00Z",
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


def _rte_winter_fixture_records() -> list[dict]:
    rows = []
    at = datetime(2022, 11, 25, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 1, 5, 23, 30, tzinfo=timezone.utc)
    while at <= end:
        local_day = at.astimezone(PARIS).date()
        target = local_day >= datetime(2023, 1, 1).date()
        rows.append({
            "code_insee_region": "11",
            "libelle_region": "Île-de-France",
            "date_heure": at.isoformat().replace("+00:00", "Z"),
            "consommation": 1200 if target else 1000,
            "nature": "Données définitives",
        })
        at += timedelta(minutes=30)
    return rows


def test_meteofrance_archive_parser_extracts_grand_froid_not_heat():
    payload = {
        "product": {
            "warning_type": "vigilance",
            "type_cdp": "CDP_CARTE_EXTERNE",
            "domain_id": "FRA",
            "update_time": "2023-01-01T06:00:00Z",
            "periods": [
                {
                    "echeance": "J",
                    "begin_validity_time": "2023-01-01T06:00:00Z",
                    "end_validity_time": "2023-01-02T06:00:00Z",
                    "timelaps": {
                        "domain_ids": [
                            {
                                "domain_id": "75",
                                "phenomenon_items": [
                                    {
                                        "phenomenon_id": "6",
                                        "phenomenon_max_color_id": 4,
                                        "timelaps_items": [
                                            {
                                                "begin_time": "2023-01-01T08:00:00Z",
                                                "end_time": "2023-01-01T18:00:00Z",
                                                "color_id": 4,
                                            }
                                        ],
                                    },
                                    {
                                        "phenomenon_id": "7",
                                        "phenomenon_max_color_id": 3,
                                        "timelaps_items": [
                                            {
                                                "begin_time": "2023-01-01T10:00:00Z",
                                                "end_time": "2023-01-02T04:00:00Z",
                                                "color_id": 3,
                                            }
                                        ],
                                    },
                                ],
                            }
                        ]
                    },
                }
            ],
        }
    }
    update_time, rows = extract_cold_intervals(payload, min_color_id=3, departments={"75"})
    assert update_time == datetime(2023, 1, 1, 6, 0, tzinfo=timezone.utc)
    assert len(rows) == 1
    assert rows[0]["department"] == "75"
    assert rows[0]["color_id"] == 3
    assert rows[0]["begin"] == datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)


def test_regional_cold_requires_two_distinct_departments():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    try:
        first = _department_cold_event(db, f"cold-first-{tag}", "75", datetime(2023, 1, 1, 8, 0, 0))
        first_result = HorizonRegionalColdService(db).aggregate(
            start_at=datetime(2023, 1, 1),
            end_at=datetime(2023, 1, 3),
        )
        assert first_result["regional_events_created"] == 0

        second = _department_cold_event(db, f"cold-second-{tag}", "92", datetime(2023, 1, 1, 9, 0, 0))
        result = HorizonRegionalColdService(db).aggregate(
            start_at=datetime(2023, 1, 1),
            end_at=datetime(2023, 1, 3),
        )
        assert result["regional_events_created"] >= 1
        regional = db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id.in_(result["regional_event_ids"])
        ).first()
        assert regional is not None
        assert regional.event_type == "extreme_cold_region"
        assert regional.geography == ["FR", "REGION:11"]
        assert regional.first_observed_at == second.first_observed_at
        assert first.id in regional.raw_facts["member_event_ids"]
        assert second.id in regional.raw_facts["member_event_ids"]
        assert regional.raw_facts["causal_claim"] is False
    finally:
        db.close()


def test_rte_heating_load_creates_covered_outcome_and_backtest_success():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    records = _rte_winter_fixture_records()
    try:
        _department_cold_event(db, f"rte-cold-first-{tag}", "75", datetime(2023, 1, 1, 8, 0, 0))
        _department_cold_event(db, f"rte-cold-second-{tag}", "92", datetime(2023, 1, 1, 9, 0, 0))

        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).startswith(RTE_REGIONAL_ENDPOINT)
            offset = int(request.url.params.get("offset", "0"))
            limit = int(request.url.params.get("limit", "100"))
            page = records[offset : offset + limit]
            return httpx.Response(200, json={"results": page, "total_count": len(records)}, request=request)

        mock = httpx.Client(transport=httpx.MockTransport(handler))
        result = HorizonRteHeatingLoadBackfillService(db).backfill(
            HorizonRteHeatingLoadBackfillRequest(
                start_at=datetime(2023, 1, 1, 0, 0, 0),
                end_at=datetime(2023, 1, 5, 23, 59, 59),
                baseline_lookback_days=28,
                minimum_lift_ratio=0.03,
                minimum_daily_points=40,
                max_records=5000,
            ),
            client=mock,
        )
        mock.close()

        assert result["regional_cold_events_considered"] >= 1
        assert "11" in result["region_codes"]
        assert result["heating_load_signal_links_created_or_reused"] >= 1
        assert result["critical_semantics"]["rte_load_proves_electric_heating_causality"] is False
        assert result["critical_semantics"]["negative_labels_require_complete_signal_coverage"] is True
        region_result = next(item for item in result["regions"] if item["region_code"] == "11")
        assert region_result["coverage_complete"] is True

        signals = db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.source == "rte-eco2mix-regional-cons-def",
            HorizonSocialSignal.signal_type == "heating_load_pressure",
        ).all()
        matching = [row for row in signals if row.signal_key.startswith("rte-heating-load:")]
        assert matching
        assert all(row.reliability == 0.94 for row in matching)
        assert all(row.normalized_score >= 1.0 for row in matching)
        assert all(row.evidence["heating_causality_proven"] is False for row in matching)

        coverage = db.query(HorizonHistoricalCoverageInterval).filter(
            HorizonHistoricalCoverageInterval.id == region_result["coverage_interval_id"]
        ).one()
        assert coverage.coverage_kind == "signal"
        assert coverage.signal_types == ["heating_load_pressure"]
        assert coverage.event_types == ["extreme_cold_region"]
        assert coverage.geography == ["FR", "REGION:11"]
        assert coverage.completeness == "complete"

        uid = f"rte-cold-backtest-{tag}"
        user_response = client.put(f"/v1/users/{uid}", json={"external_id": uid})
        assert user_response.status_code == 200, user_response.text
        backtest = client.post(
            f"/v1/horizon/backtests/users/{uid}/run",
            json={
                "start_at": "2023-01-01T00:00:00Z",
                "end_at": "2023-01-01T23:59:59Z",
                "evaluation_as_of": "2023-01-06T12:00:00Z",
                "event_types": ["extreme_cold_region"],
                "max_events": 50,
                "max_cases": 50,
            },
        )
        assert backtest.status_code == 200, backtest.text
        body = backtest.json()
        assert body["selected_cases"] >= 1
        assert body["outcomes"]["confirmed"] >= 1
        assert body["calibration_after_run"]["probability_calibration_enabled"] is False
    finally:
        db.close()


def test_cold_routes_are_mounted_on_dedicated_horizon_api():
    assert horizon_client.post(
        "/v1/horizon/cold/backfill/meteofrance", json={}
    ).status_code == 422
    assert horizon_client.post(
        "/v1/horizon/cold/backfill/rte/heating-load", json={}
    ).status_code == 422
    assert horizon_client.post(
        "/v1/horizon/cold/regions/aggregate", json={}
    ).status_code == 422

    sync = horizon_client.post("/v1/horizon/cold/response-pattern/sync")
    assert sync.status_code == 200, sync.text
    assert sync.json()["pattern_key"] == "builtin-extreme-cold-regional-heating-load-v1"
