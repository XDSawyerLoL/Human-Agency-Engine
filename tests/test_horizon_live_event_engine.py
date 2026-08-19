from datetime import datetime
from uuid import uuid4

from app.db import SessionLocal
from app.horizon_live_models import HorizonLiveIngestionRecord
from app.horizon_models import HorizonGlobalEvent
from app.services.horizon_live import (
    GDACSAdapter,
    HorizonLiveIngestionService,
    MeteoAlarmAtomAdapter,
)


def test_gdacs_parser_preserves_provider_facts_and_alert_level():
    tag = uuid4().hex[:8]
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
                "properties": {
                    "eventtype": "EQ",
                    "eventid": f"eq-{tag}",
                    "episodeid": 1,
                    "name": "Synthetic earthquake near Paris",
                    "country": "France",
                    "alertlevel": "orange",
                    "severity": 6.2,
                    "fromdate": "2026-08-19T07:00:00Z",
                    "datetime": "2026-08-19T07:06:00Z",
                },
            }
        ],
    }
    items = GDACSAdapter(endpoint="https://example.invalid/gdacs").parse(
        payload,
        fetched_at=datetime(2026, 8, 19, 7, 10),
    )
    assert len(items) == 1
    event = items[0]
    assert event.event_type == "earthquake"
    assert event.external_key.startswith("EQ:")
    assert event.raw_facts["alert_level"] == "orange"
    assert event.raw_facts["severity"] == 6.2
    assert event.raw_facts["geometry"]["type"] == "Point"
    assert event.source_reliability >= 0.95
    assert event.observed_at >= event.occurred_at


def test_meteoalarm_atom_parser_extracts_cap_behavior_relevant_fields():
    tag = uuid4().hex[:8]
    atom = f'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
      <title>MeteoAlarm France</title>
      <entry>
        <id>urn:test:heat:{tag}</id>
        <title>Orange heat warning for Ile-de-France</title>
        <updated>2026-08-19T06:30:00Z</updated>
        <summary>Exceptional heat expected.</summary>
        <link href="https://example.invalid/warning/{tag}" />
        <cap:event>Extreme high temperature</cap:event>
        <cap:severity>Severe</cap:severity>
        <cap:urgency>Expected</cap:urgency>
        <cap:certainty>Likely</cap:certainty>
        <cap:areaDesc>Ile-de-France</cap:areaDesc>
        <cap:effective>2026-08-20T06:00:00Z</cap:effective>
        <cap:expires>2026-08-22T22:00:00Z</cap:expires>
      </entry>
    </feed>'''
    items = MeteoAlarmAtomAdapter("france").parse(atom)
    assert len(items) == 1
    event = items[0]
    assert event.event_type == "weather_alert_extreme_high_temperature"
    assert event.geography == ["FR"]
    assert event.raw_facts["severity"] == "Severe"
    assert event.raw_facts["certainty"] == "Likely"
    assert event.raw_facts["area"] == "Ile-de-France"
    assert event.raw_facts["effective"] == "2026-08-20T06:00:00Z"
    assert event.source_url.endswith(tag)


def test_live_ingestion_dedupes_identical_snapshot_but_keeps_provider_update():
    tag = uuid4().hex[:8]
    adapter = GDACSAdapter(endpoint=f"https://example.invalid/gdacs/{tag}")
    base = {
        "type": "FeatureCollection",
        "features": [
            {
                "properties": {
                    "eventtype": "FL",
                    "eventid": f"flood-{tag}",
                    "episodeid": 1,
                    "name": "Synthetic flood",
                    "country": "France",
                    "alertlevel": "green",
                    "fromdate": "2026-08-19T06:00:00Z",
                    "datetime": "2026-08-19T06:05:00Z",
                }
            }
        ],
    }
    db = SessionLocal()
    try:
        service = HorizonLiveIngestionService(db)
        candidates = adapter.parse(base)
        first = service.ingest_candidates(adapter, candidates)
        second = service.ingest_candidates(adapter, candidates)
        assert first["created_snapshots"] == 1
        assert second["created_snapshots"] == 0
        assert second["duplicates"] == 1

        updated = {
            **base,
            "features": [
                {
                    "properties": {
                        **base["features"][0]["properties"],
                        "alertlevel": "orange",
                        "datetime": "2026-08-19T07:05:00Z",
                    }
                }
            ],
        }
        third = service.ingest_candidates(adapter, adapter.parse(updated))
        assert third["created_snapshots"] == 1

        records = (
            db.query(HorizonLiveIngestionRecord)
            .filter(HorizonLiveIngestionRecord.source_key == "gdacs")
            .filter(HorizonLiveIngestionRecord.external_key.like(f"%flood-{tag}%"))
            .all()
        )
        assert len(records) == 2
        events = db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id.in_([r.event_id for r in records])).all()
        levels = sorted(event.raw_facts["alert_level"] for event in events)
        assert levels == ["green", "orange"]
        assert all(event.event_key.startswith("live:gdacs:") for event in events)
    finally:
        db.close()


def test_source_parsers_require_no_network_for_backtest_or_ci():
    # Parsing and ingestion are pure with respect to provider payloads. Network is
    # only used by adapter.fetch(), so fixtures can reproduce exact historical inputs.
    gdacs = GDACSAdapter(endpoint="https://example.invalid/never-called")
    assert gdacs.parse({"features": []}) == []
    meteo = MeteoAlarmAtomAdapter("france")
    assert meteo.parse('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') == []
