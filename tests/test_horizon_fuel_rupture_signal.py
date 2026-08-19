from __future__ import annotations

from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_fuel_schemas import HorizonFuelNormalizeRequest
from app.horizon_models import HorizonSocialSignal
from app.horizon_source_models import HorizonRawObservation, HorizonSource
from app.main import app
from app.services.horizon_fuel import FUEL_RUPTURE_URL, HorizonFuelService, SOURCE_KEY

api = TestClient(app)


def _pdv(station_id: int, cp: str, *, temp_gazole: bool = False, permanent_gazole: bool = False) -> str:
    if temp_gazole:
        fuel = '<rupture id="1" fuel="Gazole" debut="2026-08-18 08:00:00" fin="" type="temporaire" />'
    elif permanent_gazole:
        fuel = '<rupture id="1" fuel="Gazole" debut="2020-01-01 00:00:00" fin="" type="definitive" />'
    else:
        fuel = '<prix nom="Gazole" id="1" maj="2026-08-19 08:00:00" valeur="1.899" />'
    permanent_sp95 = '<rupture id="2" fuel="SP95" debut="2020-01-01 00:00:00" fin="" type="definitive" />'
    return (
        f'<pdv id="{station_id}" latitude="4880000" longitude="230000" cp="{cp}" pop="R">'
        f'<adresse>fixture</adresse><ville>fixture</ville>{fuel}{permanent_sp95}</pdv>'
    )


def _feed_zip() -> bytes:
    rows = []
    for index in range(10):
        rows.append(_pdv(920000 + index, "92100", temp_gazole=index < 4))
    rows.append(_pdv(929999, "92100", permanent_gazole=True))
    for index in range(5):
        rows.append(_pdv(290000 + index, "29000", temp_gazole=index == 0))

    xml = ('<?xml version="1.0" encoding="UTF-8"?><pdv_liste>' + "".join(rows) + "</pdv_liste>").encode()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("PrixCarburants_instantane.xml", xml)
    return output.getvalue()


def _network(content: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == FUEL_RUPTURE_URL
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "application/zip"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _create_user(uid: str, department: str):
    created = api.put(
        f"/v1/users/{uid}",
        json={"external_id": uid, "country": "FR", "currency": "EUR", "timezone": "Europe/Paris"},
    )
    assert created.status_code == 200, created.text
    fact = api.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "location",
            "key": "department",
            "value": {"code": department},
            "source": "user",
            "confidence": 1.0,
            "sensitivity": "personal",
        },
    )
    assert fact.status_code == 200, fact.text


def test_official_fuel_feed_excludes_definitive_non_distribution_and_builds_material_snapshot():
    content = _feed_zip()
    network = _network(content)
    db = SessionLocal()
    try:
        first = HorizonFuelService(db).poll(client=network)
        assert first["new_observations"] == 1
        assert first["temporary_ruptures_only"] is True
        assert first["promoted_events"] == 0

        source = db.query(HorizonSource).filter(HorizonSource.source_key == SOURCE_KEY).one()
        assert source.source_class == "official_primary"
        assert source.metadata_json["definitive_non_distribution_excluded"] is True

        observation = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == first["observation_id"]
        ).one()
        facts = observation.canonical_facts
        gazole_92 = facts["department_fuels"]["92"]["Gazole"]
        assert gazole_92["reporting_stations"] == 10
        assert gazole_92["temporary_ruptures"] == 4
        assert gazole_92["temporary_rupture_rate"] == 0.4
        assert "SP95" not in facts["department_fuels"]["92"]
        assert observation.raw_metadata["raw_station_rows_persisted"] is False

        second = HorizonFuelService(db).poll(client=network)
        assert second["new_observations"] == 0
        assert second["replayed_observations"] == 1
        assert second["observation_id"] == first["observation_id"]
    finally:
        db.close()
        network.close()


def test_fuel_normalizer_creates_scoped_event_and_out_of_sequence_stock_signal_without_inventing_panic():
    content = _feed_zip()
    network = _network(content)
    db = SessionLocal()
    try:
        HorizonFuelService(db).poll(client=network)
        normalized = HorizonFuelService(db).normalize_latest(HorizonFuelNormalizeRequest())
        assert normalized["events_created_or_reused"] == 1
        event = normalized["events"][0]
        assert event["department"] == "92"
        assert event["fuel"] == "Gazole"
        assert event["reporting_stations"] == 10
        assert event["temporary_ruptures"] == 4
        assert event["temporary_rupture_rate"] == 0.4
        assert event["personal_scope"]["all"][0]["value"] == "92"

        signal = db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.id == event["stock_signal_id"]
        ).one()
        assert signal.signal_type == "stock_availability"
        assert signal.direction == "down"
        assert signal.value == 0.6
        assert signal.reliability == 0.96
        assert signal.evidence["temporary_rupture_rate"] == 0.4
        assert "panic_buying" in signal.evidence["does_not_measure"]
        assert "cause_of_rupture" in signal.evidence["does_not_measure"]

        again = HorizonFuelService(db).normalize_latest(HorizonFuelNormalizeRequest())
        assert again["events"][0]["event_id"] == event["event_id"]
        assert again["events"][0]["stock_signal_id"] == event["stock_signal_id"]
        assert again["events"][0]["stock_signal_created"] is False
        event_id = event["event_id"]
    finally:
        db.close()
        network.close()

    library = api.post("/v1/horizon/response-library/builtins/sync")
    assert library.status_code == 200, library.text
    supply = next(
        item
        for item in library.json()["patterns"]
        if item["pattern_key"] == "builtin-supply-risk-precautionary-buying-v1"
    )
    cascade = api.post(
        "/v1/horizon/cascades/project",
        json={"event_id": event_id, "pattern_id": supply["id"], "mode": "live"},
    )
    assert cascade.status_code == 200, cascade.text
    body = cascade.json()
    assert body["current_stage"] == "pre-cascade / latent"
    stock_stage = next(item for item in body["stages"] if item["stage"] == "queue and inventory pressure")
    assert stock_stage["state"] in {"active", "established"}
    assert stock_stage["sequentially_reached"] is False
    assert body["interpretation"]["out_of_sequence_signal_count"] >= 1

    local_uid = f"fuel-local-{uuid4().hex[:8]}"
    remote_uid = f"fuel-remote-{uuid4().hex[:8]}"
    _create_user(local_uid, "92")
    _create_user(remote_uid, "29")

    local = api.post(
        f"/v1/horizon/impact/users/{local_uid}/assess",
        json={"event_id": event_id, "pattern_id": supply["id"], "mode": "live"},
    )
    remote = api.post(
        f"/v1/horizon/impact/users/{remote_uid}/assess",
        json={"event_id": event_id, "pattern_id": supply["id"], "mode": "live"},
    )
    assert local.status_code == 200, local.text
    assert remote.status_code == 200, remote.text
    assert local.json()["assessment"]["personal_exposure_layer"]["personal_scope"]["status"] == "matched"
    assert local.json()["assessment"]["attention_score"] > 0
    assert remote.json()["assessment"]["personal_exposure_layer"]["personal_scope"]["status"] == "mismatched"
    assert remote.json()["assessment"]["attention_score"] == 0.0
    assert remote.json()["assessment"]["attention_band"] == "silent"


def test_fuel_routes_are_mounted_without_live_network(monkeypatch):
    def fake_poll(self, *, client=None):
        return {
            "source_key": SOURCE_KEY,
            "new_observations": 1,
            "replayed_observations": 0,
            "observation_id": 42,
            "feed_hash": "fixture",
            "temporary_ruptures_only": True,
            "stations": 123,
            "promoted_events": 0,
        }

    def fake_normalize(self, request):
        return {
            "source_observation_id": 42,
            "normalizer_version": "horizon-fr-fuel-rupture-v0.1",
            "events_created_or_reused": 0,
            "events": [],
            "temporary_ruptures_only": True,
            "definitive_non_distribution_excluded": True,
            "raw_station_rows_persisted": False,
        }

    monkeypatch.setattr(HorizonFuelService, "poll", fake_poll)
    monkeypatch.setattr(HorizonFuelService, "normalize_latest", fake_normalize)

    poll = api.post("/v1/horizon/live/fuel-ruptures/poll")
    assert poll.status_code == 200, poll.text
    assert poll.json()["temporary_ruptures_only"] is True

    normalized = api.post("/v1/horizon/normalize/fuel-ruptures/latest", json={})
    assert normalized.status_code == 200, normalized.text
    assert normalized.json()["raw_station_rows_persisted"] is False
