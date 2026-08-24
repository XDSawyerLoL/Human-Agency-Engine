from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonRawObservation, HorizonSource
from app.horizon_supply_trigger_schemas import HorizonGdeltFuelSupplyTriggerBackfillRequest
from app.services.horizon_gdelt1_supply_trigger import (
    GDELT_EVENTS_BASE_URL,
    HorizonGdeltFuelSupplyTriggerBackfillService,
    SOURCE_KEY,
)


client = TestClient(app)


def _row(
    *,
    event_id: int,
    sql_date: str,
    date_added: str,
    event_code: str,
    domain: str,
    url_slug: str,
    country: str = "FR",
    root: str = "1",
    actor1: str = "WORKERS",
    actor2: str = "TOTALENERGIES",
) -> str:
    values = [""] * 58
    values[0] = str(event_id)
    values[1] = sql_date
    values[6] = actor1
    values[16] = actor2
    values[25] = root
    values[26] = event_code
    values[27] = event_code[:3]
    values[28] = "14"
    values[29] = "4"
    values[31] = "6"
    values[32] = "2"
    values[33] = "6"
    values[50] = "France"
    values[51] = country
    values[52] = "FR00"
    values[56] = date_added
    values[57] = f"https://{domain}/{url_slug}"
    return "\t".join(values)


def _daily_zip(rows: list[str], day: str) -> bytes:
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{day}.export.CSV", payload)
    return output.getvalue()


def _network(files: dict[str, bytes]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        name = str(request.url).rsplit("/", 1)[-1]
        day = name.split(".", 1)[0]
        assert str(request.url) == f"{GDELT_EVENTS_BASE_URL}/{name}"
        content = files[day]
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "application/zip"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_gdelt_daily_replay_builds_media_report_cluster_without_confirming_supply_disruption():
    files = {
        "20221010": _daily_zip(
            [
                _row(
                    event_id=1001,
                    sql_date="20221010",
                    date_added="20221010081500",
                    event_code="143",
                    domain="example-one.fr",
                    url_slug="greve-raffinerie-totalenergies-carburant",
                ),
                _row(
                    event_id=1002,
                    sql_date="20221010",
                    date_added="20221010090000",
                    event_code="1442",
                    domain="example-two.com",
                    url_slug="blocage-depot-fuel-diesel",
                ),
                _row(
                    event_id=1003,
                    sql_date="20221010",
                    date_added="20221010093000",
                    event_code="143",
                    domain="example-three.com",
                    url_slug="teachers-strike",
                    actor2="GOVERNMENT",
                ),
                _row(
                    event_id=1004,
                    sql_date="20221010",
                    date_added="20221010100000",
                    event_code="143",
                    domain="example-four.com",
                    url_slug="refinery-strike",
                    country="US",
                ),
            ],
            "20221010",
        ),
        "20221011": _daily_zip(
            [
                _row(
                    event_id=2001,
                    sql_date="20221011",
                    date_added="20221011073000",
                    event_code="143",
                    domain="only-one-domain.fr",
                    url_slug="raffinerie-gazole-strike",
                ),
            ],
            "20221011",
        ),
    }
    network = _network(files)
    db = SessionLocal()
    try:
        request = HorizonGdeltFuelSupplyTriggerBackfillRequest(
            start_at=datetime.fromisoformat("2022-10-10T00:00:00"),
            end_at=datetime.fromisoformat("2022-10-11T23:59:59"),
            min_distinct_domains_per_day=2,
        )
        result = HorizonGdeltFuelSupplyTriggerBackfillService(db).backfill(
            request,
            client=network,
        )
        assert result["replayed_existing_run"] is False
        assert result["days_requested"] == 2
        assert result["days_downloaded"] == 2
        assert result["download_failures"] == []
        assert result["raw_observations_created"] == 3
        assert result["report_clusters_created"] == 1
        assert result["event_coverage_complete"] is True
        assert result["critical_semantics"]["trigger_is_media_precursor"] is True
        assert result["critical_semantics"]["trigger_is_underlying_disruption_confirmation"] is False
        assert result["critical_semantics"]["source_count_is_truth_vote"] is False

        source = db.query(HorizonSource).filter(HorizonSource.source_key == SOURCE_KEY).one()
        assert source.source_class == "news_global"
        assert source.metadata_json["media_report_cluster_is_real_world_disruption_confirmation"] is False

        observations = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id
        ).order_by(HorizonRawObservation.observed_at.asc()).all()
        assert len(observations) == 3
        assert observations[0].canonical_facts["cameo_event_code"] == "143"
        assert observations[0].canonical_facts["underlying_disruption_confirmed"] is False
        assert observations[0].raw_metadata["article_body_fetched"] is False

        event = db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.event_type == "fuel_supply_disruption_report_cluster"
        ).one()
        assert event.geography == ["FR"]
        assert event.first_observed_at == datetime.fromisoformat("2022-10-10T08:15:00")
        assert event.raw_facts["distinct_source_domain_count"] == 2
        assert event.raw_facts["underlying_disruption_confirmed"] is False
        assert event.raw_facts["cluster_threshold_is_truth_vote"] is False

        replay = HorizonGdeltFuelSupplyTriggerBackfillService(db).backfill(
            request,
            client=network,
        )
        assert replay["replayed_existing_run"] is True
        assert replay["run_id"] == result["run_id"]
    finally:
        db.close()
        network.close()


def test_gdelt_trigger_backfill_route_is_mounted_without_live_network(monkeypatch):
    def fake_backfill(self, request, *, client=None):
        return {
            "engine": "horizon-gdelt1-fuel-supply-trigger-v0.1",
            "days_requested": 2,
            "report_clusters_created": 1,
            "event_coverage_complete": True,
            "critical_semantics": {
                "trigger_is_media_precursor": True,
                "trigger_is_underlying_disruption_confirmation": False,
                "numeric_probabilities_enabled": False,
            },
        }

    monkeypatch.setattr(
        HorizonGdeltFuelSupplyTriggerBackfillService,
        "backfill",
        fake_backfill,
    )
    response = client.post(
        "/v1/horizon/world/backfill/fuel-supply-trigger",
        json={
            "start_at": "2022-10-10T00:00:00",
            "end_at": "2022-10-11T23:59:59",
            "min_distinct_domains_per_day": 2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["report_clusters_created"] == 1
    assert response.json()["critical_semantics"]["trigger_is_underlying_disruption_confirmation"] is False
