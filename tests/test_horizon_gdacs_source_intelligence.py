from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.db import SessionLocal
from app.horizon_global_alert_schemas import HorizonGdacsPollRequest
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from app.services.horizon_gdacs import GDACS_SEARCH_ENDPOINT, HorizonGdacsService
from app.services.horizon_global_alert_normalizer import HorizonGlobalAlertNormalizer


def _payload(tag: str, *, alert_level: str = "orange", updated: str = "2026-08-19T07:06:00Z") -> dict:
    return {
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
                    "iso3": "FRA",
                    "alertlevel": alert_level,
                    "severity": 6.2,
                    "population": 100000,
                    "fromdate": "2026-08-19T07:00:00Z",
                    "datetime": updated,
                },
            }
        ],
    }


def test_gdacs_writes_raw_snapshot_only_preserves_provider_time_and_normalizes_unconfirmed():
    db = SessionLocal()
    tag = uuid4().hex[:8]
    current_payload = _payload(tag)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(GDACS_SEARCH_ENDPOINT)
        return httpx.Response(200, json=current_payload, request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    request = HorizonGdacsPollRequest(
        event_types=["EQ"],
        alert_levels=["orange", "red"],
        lookback_days=4,
        page_size=100,
        max_pages=2,
    )
    fetched_at = datetime(2026, 8, 19, 7, 10, tzinfo=timezone.utc)
    try:
        before_events = db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.source == "gdacs-official").count()
        first = HorizonGdacsService(db).poll(request, client=mock, observed_at=fetched_at)
        assert first["new_observations"] == 1
        assert first["critical_semantics"]["adapter_creates_confirmed_event"] is False
        assert db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.source == "gdacs-official").count() == before_events

        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdacs-official").one()
        assert source.source_class == "official_multilateral"
        assert source.metadata_json["independence_family"] == "gdacs"
        observation = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == first["observation_ids"][0]
        ).one()
        assert observation.observation_type == "multilateral_disaster_alert_snapshot"
        assert observation.published_at == datetime(2026, 8, 19, 7, 6)
        assert observation.observed_at == datetime(2026, 8, 19, 7, 10)
        assert observation.event_time == datetime(2026, 8, 19, 7, 0)
        assert observation.canonical_facts["alert_level"] == "orange"
        assert observation.raw_metadata["geometry"]["type"] == "Point"

        normalized = HorizonGlobalAlertNormalizer(db).normalize_latest_gdacs(max_observations=10)
        assert normalized["normalized"] == 1
        assert normalized["events_promoted"] == 0
        candidate_id = normalized["candidates"][0]["candidate_id"]
        candidate = db.query(HorizonEventCandidate).filter(HorizonEventCandidate.id == candidate_id).one()
        assert candidate.event_type == "earthquake"
        assert candidate.promotion_status == "candidate"
        assert candidate.promoted_event_id is None
        assert normalized["candidates"][0]["promotion_readiness"]["ready"] is False

        replay = HorizonGdacsService(db).poll(
            request,
            client=mock,
            observed_at=datetime(2026, 8, 19, 7, 20, tzinfo=timezone.utc),
        )
        assert replay["new_observations"] == 0
        assert replay["replayed_observations"] == 1

        current_payload = _payload(tag, alert_level="red", updated="2026-08-19T08:06:00Z")
        updated = HorizonGdacsService(db).poll(
            request,
            client=mock,
            observed_at=datetime(2026, 8, 19, 8, 10, tzinfo=timezone.utc),
        )
        assert updated["new_observations"] == 1
        source_rows = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id
        ).all()
        snapshots = [
            row for row in source_rows
            if row.canonical_facts.get("event_id") == f"eq-{tag}"
        ]
        assert len(snapshots) == 2
        assert sorted(row.canonical_facts["alert_level"] for row in snapshots) == ["orange", "red"]
    finally:
        mock.close()
        db.close()
