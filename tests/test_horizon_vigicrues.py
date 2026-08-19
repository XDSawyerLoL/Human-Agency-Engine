from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.db import SessionLocal
from app.horizon_convergence_schemas import HorizonVigicruesPollRequest
from app.horizon_models import HorizonGlobalEvent
from app.services.horizon_vigicrues import HorizonVigicruesService, VIGICRUES_GEOJSON_ENDPOINT


def test_vigicrues_promotes_only_thresholded_official_risk_and_replays_idempotently():
    db = SessionLocal()
    tag = uuid4().hex[:8]
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": f"green-{tag}",
                "properties": {"CdEntCru": f"G{tag}", "lbentcru": "Green river", "NivInfViCr": 1},
                "geometry": {"type": "LineString", "coordinates": [[2.0, 48.0], [2.1, 48.1]]},
            },
            {
                "type": "Feature",
                "id": f"orange-{tag}",
                "properties": {"CdEntCru": f"O{tag}", "lbentcru": "Orange river", "NivInfViCr": 3},
                "geometry": {"type": "LineString", "coordinates": [[2.2, 48.2], [2.3, 48.3]]},
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == VIGICRUES_GEOJSON_ENDPOINT
        return httpx.Response(200, json=payload, request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    request = HorizonVigicruesPollRequest(minimum_level=2, max_features=10)
    observed_at = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    try:
        first = HorizonVigicruesService(db).poll(request, client=mock, observed_at=observed_at)
        assert first["new_observations"] == 1
        assert first["features_ignored_below_threshold"] == 1
        assert first["promoted_events_created_or_reused"] == 1
        event = db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id == first["event_ids"][0]
        ).one()
        assert event.event_type == "river_flood_risk"
        assert event.source == "vigicrues-official"
        assert event.raw_facts["normalized_facts"]["vigilance_level"] == 3
        assert event.raw_facts["normalized_facts"]["physical_state_not_behavior"] is True

        second = HorizonVigicruesService(db).poll(request, client=mock, observed_at=observed_at)
        assert second["new_observations"] == 0
        assert second["replayed_observations"] == 1
        assert second["event_ids"] == first["event_ids"]
    finally:
        mock.close()
        db.close()
