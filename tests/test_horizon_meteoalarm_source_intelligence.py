from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.db import SessionLocal
from app.horizon_global_alert_schemas import HorizonMeteoAlarmPollRequest
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from app.services.horizon_global_alert_normalizer import HorizonGlobalAlertNormalizer
from app.services.horizon_meteoalarm import HorizonMeteoAlarmService, METEOALARM_ATOM_TEMPLATE


def _atom(tag: str, *, severity: str = "Severe", updated: str = "2026-08-19T06:30:00Z") -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
      <title>MeteoAlarm France</title>
      <entry>
        <id>urn:test:heat:{tag}</id>
        <title>Orange heat warning for Ile-de-France</title>
        <updated>{updated}</updated>
        <summary>Exceptional heat expected.</summary>
        <link href="https://example.invalid/warning/{tag}" />
        <cap:event>Extreme high temperature</cap:event>
        <cap:severity>{severity}</cap:severity>
        <cap:urgency>Expected</cap:urgency>
        <cap:certainty>Likely</cap:certainty>
        <cap:areaDesc>Ile-de-France</cap:areaDesc>
        <cap:effective>2026-08-20T06:00:00Z</cap:effective>
        <cap:expires>2026-08-22T22:00:00Z</cap:expires>
      </entry>
    </feed>'''.encode("utf-8")


def test_meteoalarm_atom_writes_raw_relay_only_and_normalizes_without_promotion():
    db = SessionLocal()
    tag = uuid4().hex[:8]
    current_atom = _atom(tag)
    endpoint = METEOALARM_ATOM_TEMPLATE.format(country="france")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == endpoint
        return httpx.Response(
            200,
            content=current_atom,
            headers={"content-type": "application/atom+xml"},
            request=request,
        )

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    request = HorizonMeteoAlarmPollRequest(countries=["france"], max_entries_per_country=10)
    fetched_at = datetime(2026, 8, 19, 6, 35, tzinfo=timezone.utc)
    try:
        before_events = db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.source.like("meteoalarm:%")).count()
        first = HorizonMeteoAlarmService(db).poll(request, client=mock, observed_at=fetched_at)
        assert first["countries_succeeded"] == 1
        assert first["countries_failed"] == 0
        assert first["new_observations"] == 1
        assert first["critical_semantics"]["adapter_creates_confirmed_event"] is False
        assert db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.source.like("meteoalarm:%")).count() == before_events

        source = db.query(HorizonSource).filter(HorizonSource.source_key == "meteoalarm:france").one()
        assert source.source_class == "official_aggregator"
        assert source.metadata_json["independence_family"] == "weather-warning:france"
        observation = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == first["observation_ids"][0]
        ).one()
        assert observation.observation_type == "official_weather_warning_aggregated_snapshot"
        assert observation.published_at == datetime(2026, 8, 19, 6, 30)
        assert observation.observed_at == datetime(2026, 8, 19, 6, 35)
        assert observation.event_time == datetime(2026, 8, 20, 6, 0)
        assert observation.canonical_facts["severity"] == "Severe"
        assert observation.canonical_facts["certainty"] == "Likely"
        assert observation.canonical_facts["area"] == "Ile-de-France"

        normalized = HorizonGlobalAlertNormalizer(db).normalize_latest_meteoalarm(max_observations=10)
        assert normalized["normalized"] == 1
        assert normalized["events_promoted"] == 0
        own = normalized["candidates"][0]
        candidate = db.query(HorizonEventCandidate).filter(HorizonEventCandidate.id == own["candidate_id"]).one()
        assert candidate.event_type == "extreme_heat"
        assert candidate.promotion_status == "candidate"
        assert candidate.promoted_event_id is None
        assert own["promotion_readiness"]["ready"] is False

        replay = HorizonMeteoAlarmService(db).poll(
            request,
            client=mock,
            observed_at=datetime(2026, 8, 19, 6, 45, tzinfo=timezone.utc),
        )
        assert replay["new_observations"] == 0
        assert replay["replayed_observations"] == 1

        current_atom = _atom(tag, severity="Extreme", updated="2026-08-19T07:30:00Z")
        updated = HorizonMeteoAlarmService(db).poll(
            request,
            client=mock,
            observed_at=datetime(2026, 8, 19, 7, 35, tzinfo=timezone.utc),
        )
        assert updated["new_observations"] == 1
        rows = db.query(HorizonRawObservation).filter(HorizonRawObservation.source_id == source.id).all()
        own_rows = [
            row for row in rows
            if row.canonical_facts.get("canonical_warning_id") == f"urn:test:heat:{tag}"
        ]
        assert len(own_rows) == 2
        assert sorted(row.canonical_facts["severity"] for row in own_rows) == ["Extreme", "Severe"]
    finally:
        mock.close()
        db.close()


def test_meteoalarm_country_failure_is_isolated():
    db = SessionLocal()
    endpoints = {
        country: METEOALARM_ATOM_TEMPLATE.format(country=country)
        for country in ("france", "belgium")
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == endpoints["france"]:
            return httpx.Response(200, content=_atom("isolated"), request=request)
        return httpx.Response(503, content=b"upstream unavailable", request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = HorizonMeteoAlarmService(db).poll(
            HorizonMeteoAlarmPollRequest(countries=["france", "belgium"], max_entries_per_country=10),
            client=mock,
            observed_at=datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc),
        )
        assert result["countries_succeeded"] == 1
        assert result["countries_failed"] == 1
        assert result["new_observations"] == 1
        assert result["errors"][0]["country"] == "belgium"
    finally:
        mock.close()
        db.close()
