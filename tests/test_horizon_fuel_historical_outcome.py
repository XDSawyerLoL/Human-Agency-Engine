from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_api import app
from app.horizon_backfill_models import HorizonHistoricalCoverageInterval
from app.horizon_fuel_schemas import HorizonFuelHistoricalBackfillRequest
from app.horizon_source_models import HorizonRawObservation, HorizonSource
from app.services.horizon_fuel_history import (
    ANNUAL_ARCHIVE_BASE_URL,
    HorizonFuelHistoricalBackfillService,
    SOURCE_KEY,
)


client = TestClient(app)


def _station(station_id: int, cp: str, *, disrupted: bool = False) -> str:
    rupture = (
        '<rupture id="1" fuel="Gazole" debut="2025-01-10 08:00:00" '
        'fin="2025-01-12 00:00:00" type="temporaire" />'
        if disrupted
        else ""
    )
    return (
        f'<pdv id="{station_id}" latitude="4880000" longitude="230000" cp="{cp}" pop="R">'
        '<adresse>fixture</adresse><ville>fixture</ville>'
        '<prix nom="Gazole" id="1" maj="2025-01-09 08:00:00" valeur="1.899" />'
        f"{rupture}</pdv>"
    )


def _archive_zip() -> bytes:
    rows = [_station(920000 + i, "92100", disrupted=i < 4) for i in range(10)]
    rows.extend(_station(290000 + i, "29000", disrupted=i == 0) for i in range(5))
    xml = ('<?xml version="1.0" encoding="UTF-8"?><pdv_liste>' + "".join(rows) + "</pdv_liste>").encode()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("PrixCarburants_annuel_2025.xml", xml)
    return output.getvalue()


def _network(content: bytes) -> httpx.Client:
    expected = f"{ANNUAL_ARCHIVE_BASE_URL}/2025"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == expected
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "application/zip"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_official_annual_fuel_archive_builds_coverage_aware_historical_outcome_stream():
    network = _network(_archive_zip())
    db = SessionLocal()
    try:
        request = HorizonFuelHistoricalBackfillRequest(
            year=2025,
            min_reporting_stations=5,
            min_temporary_ruptures=3,
            min_rupture_rate=0.10,
        )
        first = HorizonFuelHistoricalBackfillService(db).backfill(request, client=network)
        assert first["replayed_existing_run"] is False
        assert first["qualifying_pressure_days"] == 2
        assert first["observations_created"] == 2
        assert first["signal_coverage_complete"] is True
        assert first["critical_semantics"]["outcome_replay_only"] is True
        assert first["critical_semantics"]["historical_trigger_replay_provided"] is False
        assert first["critical_semantics"]["daily_metric_is_instantaneous_stockout_rate"] is False

        source = db.query(HorizonSource).filter(HorizonSource.source_key == SOURCE_KEY).one()
        assert source.source_class == "official_statistical"
        assert source.metadata_json["archive_available_from"] == 2007

        rows = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.observation_type == "official_fuel_rupture_archive_daily",
        ).order_by(HorizonRawObservation.observed_at.asc()).all()
        assert len(rows) == 2
        facts = rows[0].canonical_facts
        assert facts["department"] == "92"
        assert facts["fuel"] == "Gazole"
        assert facts["reporting_stations_annual_offering_set"] == 10
        assert facts["stations_with_temporary_rupture_during_day"] == 4
        assert facts["daily_temporary_rupture_station_share"] == 0.4
        assert facts["outcome_signal_type"] == "fuel_stockout_pressure"
        assert rows[0].geography == ["FR", "DEP:92"]
        assert rows[0].raw_metadata["archive_retrieval_time_is_not_used_as_historical_event_time"] is True

        coverage = db.query(HorizonHistoricalCoverageInterval).filter(
            HorizonHistoricalCoverageInterval.id == first["signal_coverage_interval_id"]
        ).one()
        assert coverage.completeness == "complete"
        assert coverage.signal_types == ["fuel_stockout_pressure"]
        assert "DEP:92" in coverage.geography
        assert coverage.provenance["historical_trigger_replay_provided"] is False

        replay = HorizonFuelHistoricalBackfillService(db).backfill(request, client=network)
        assert replay["replayed_existing_run"] is True
        assert replay["run_id"] == first["run_id"]
    finally:
        db.close()
        network.close()


def test_fuel_historical_backfill_route_is_mounted_without_network(monkeypatch):
    def fake_backfill(self, request, *, client=None):
        return {
            "engine": "horizon-fr-fuel-historical-outcome-v0.1",
            "year": request.year,
            "observations_created": 0,
            "signal_coverage_complete": True,
            "critical_semantics": {
                "outcome_replay_only": True,
                "historical_trigger_replay_provided": False,
                "numeric_probabilities_enabled": False,
            },
        }

    monkeypatch.setattr(HorizonFuelHistoricalBackfillService, "backfill", fake_backfill)
    response = client.post(
        "/v1/horizon/backfill/fuel-ruptures",
        json={
            "year": 2025,
            "min_reporting_stations": 5,
            "min_temporary_ruptures": 3,
            "min_rupture_rate": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["year"] == 2025
    assert response.json()["critical_semantics"]["outcome_replay_only"] is True
