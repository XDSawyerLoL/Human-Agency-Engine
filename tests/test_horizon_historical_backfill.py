from copy import deepcopy
from datetime import datetime

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_backfill_models import HorizonHistoricalCoverageInterval
from app.horizon_backfill_schemas import HorizonMeteoFranceArchiveBackfillRequest
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonRawObservation
from app.main import app
from app.services.horizon_backfill import (
    METEOFRANCE_ARCHIVE_BASE_URL,
    METEOFRANCE_ARCHIVE_TREE_URL,
    HorizonHistoricalBackfillService,
    discover_carte_urls,
    extract_heat_intervals,
)

client = TestClient(app)


ARCHIVE_FILENAME = "T_QGFR40_C_LFPW_20230618060000_CDP_CARTE_EXTERNE.json"
ARCHIVE_URL = f"{METEOFRANCE_ARCHIVE_BASE_URL}2023/06/18/{ARCHIVE_FILENAME}"

TREE_FIXTURE = {
    "children": [
        {
            "path": "2023/06/18",
            "files": [
                {"name": ARCHIVE_FILENAME},
                {"name": "README.txt"},
            ],
        }
    ]
}

CARTE_FIXTURE = {
    "product": {
        "warning_type": "vigilance",
        "type_cdp": "cdp_carte_externe",
        "update_time": "2023-06-18T06:00:00Z",
        "domain_id": "FRA",
        "periods": [
            {
                "echeance": "J",
                "begin_validity_time": "2023-06-18T06:00:00Z",
                "end_validity_time": "2023-06-19T00:00:00Z",
                "timelaps": {
                    "domain_ids": [
                        {
                            "domain_id": "75",
                            "phenomenon_items": [
                                {
                                    "phenomenon_id": "6",
                                    "phenomenon_max_color_id": 3,
                                    "timelaps_items": [
                                        {
                                            "begin_time": "2023-06-18T12:00:00Z",
                                            "end_time": "2023-06-18T20:00:00Z",
                                            "color_id": 3,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            }
        ],
    },
    "meta": {"snapshot_id": "fixture-1"},
}


def _mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == METEOFRANCE_ARCHIVE_TREE_URL:
            return httpx.Response(200, json=TREE_FIXTURE, request=request)
        if str(request.url) == ARCHIVE_URL:
            return httpx.Response(200, json=CARTE_FIXTURE, request=request)
        return httpx.Response(404, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_archive_tree_discovery_and_heat_parser_are_provider_timestamped():
    urls = discover_carte_urls(TREE_FIXTURE)
    assert urls == [ARCHIVE_URL]

    update_time, rows = extract_heat_intervals(
        CARTE_FIXTURE,
        min_color_id=3,
        departments={"75"},
    )
    assert update_time.isoformat() == "2023-06-18T06:00:00+00:00"
    assert len(rows) == 1
    assert rows[0]["department"] == "75"
    assert rows[0]["color_id"] == 3
    assert rows[0]["begin"].isoformat() == "2023-06-18T12:00:00+00:00"
    assert rows[0]["end"].isoformat() == "2023-06-18T20:00:00+00:00"


def test_heat_parser_does_not_mistake_department_10_for_a_non_department_domain():
    aube = deepcopy(CARTE_FIXTURE)
    aube["product"]["periods"][0]["timelaps"]["domain_ids"][0]["domain_id"] = "10"
    _, rows = extract_heat_intervals(aube, min_color_id=3, departments={"10"})
    assert len(rows) == 1
    assert rows[0]["department"] == "10"


def test_meteofrance_archive_backfill_preserves_historical_availability_and_event_only_coverage():
    db = SessionLocal()
    mock = _mock_client()
    try:
        service = HorizonHistoricalBackfillService(db)
        request = HorizonMeteoFranceArchiveBackfillRequest(
            start_at=datetime.fromisoformat("2023-06-18T00:00:00"),
            end_at=datetime.fromisoformat("2023-06-18T23:59:59"),
            departments=["75"],
            min_color_id=3,
            max_snapshots=10,
            merge_gap_hours=24,
        )
        first = service.backfill_meteofrance_vigilance(request, client=mock)

        assert first["engine"] == "horizon-historical-backfill-v0.1"
        assert first["snapshots_in_window"] == 1
        assert first["snapshots_succeeded"] == 1
        assert first["observations_created"] == 1
        assert first["events_promoted"] == 1
        assert first["event_coverage_complete"] is True
        assert first["critical_semantics"]["historical_observed_at_uses_provider_update_time"] is True
        assert first["critical_semantics"]["historical_event_time_uses_provider_update_time"] is True
        assert first["critical_semantics"]["warning_validity_start_is_not_treated_as_already_occurred"] is True
        assert first["critical_semantics"]["adapter_directly_creates_confirmed_event"] is False
        assert first["critical_semantics"]["archive_event_coverage_is_materialization_signal_coverage"] is False

        observation = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_url == ARCHIVE_URL
        ).one()
        assert observation.observed_at.isoformat() == "2023-06-18T06:00:00"
        assert observation.published_at.isoformat() == "2023-06-18T06:00:00"
        assert observation.event_time.isoformat() == "2023-06-18T06:00:00"
        assert observation.canonical_facts["phenomenon"] == "canicule"
        assert observation.canonical_facts["begin_validity_time"] == "2023-06-18T12:00:00+00:00"

        event = db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id.in_(first["promoted_event_ids"])
        ).one()
        assert event.event_type == "extreme_heat"
        assert event.source == "meteofrance-vigilance-archive"
        assert event.first_observed_at.isoformat() == "2023-06-18T06:00:00"
        assert event.occurred_at.isoformat() == "2023-06-18T06:00:00"
        assert event.first_observed_at == event.occurred_at

        coverage = db.query(HorizonHistoricalCoverageInterval).filter(
            HorizonHistoricalCoverageInterval.id == first["event_coverage_interval_id"]
        ).one()
        assert coverage.coverage_kind == "event"
        assert coverage.event_types == ["extreme_heat"]
        assert coverage.signal_types == []
        assert coverage.completeness == "complete"
        assert coverage.provenance["does_not_cover_behavioral_materialization_signals"] is True

        second = service.backfill_meteofrance_vigilance(request, client=mock)
        assert second["run_id"] == first["run_id"]
        assert second["run_key"] == first["run_key"]
        assert second["replayed_existing_run"] is True
    finally:
        mock.close()
        db.close()


def test_backfill_routes_are_mounted_without_live_network_access():
    runs = client.get("/v1/horizon/backfill/runs")
    assert runs.status_code == 200, runs.text
    coverage = client.get("/v1/horizon/backfill/coverage")
    assert coverage.status_code == 200, coverage.text
