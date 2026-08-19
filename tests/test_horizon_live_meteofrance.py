from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from app.main import app
from app.services.horizon_meteofrance import (
    METEOFRANCE_TOKEN_ENDPOINT,
    METEOFRANCE_VIGILANCE_ENDPOINT,
    HorizonMeteoFranceService,
)

api = TestClient(app)


def _vigilance_payload(tag: str, *, global_color: str = "3") -> dict:
    return {
        "product": {
            "warning_type": "vigilance",
            "type_cdp": "cdp_carte_externe",
            "version_vigilance": "V6",
            "version_cdp": "1.0.0",
            "update_time": "2026-08-19T08:00:45Z",
            "domain_id": "FRA",
            "global_max_color_id": global_color,
            "periods": [
                {
                    "echeance": "J",
                    "begin_validity_time": "2026-08-19T08:00:00Z",
                    "end_validity_time": "2026-08-19T23:00:00Z",
                    "text_items": {"text": ["Synthetic vigilance fixture."]},
                    "timelaps": {
                        "domain_ids": [
                            {
                                "domain_id": "75",
                                "max_color_id": 3,
                                "phenomenon_items": [
                                    {
                                        "phenomenon_id": "6",
                                        "phenomenon_max_color_id": 3,
                                        "timelaps_items": [
                                            {
                                                "begin_time": "2026-08-19T10:00:00Z",
                                                "end_time": "2026-08-19T20:00:00Z",
                                                "color_id": 3,
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "domain_id": "29",
                                "max_color_id": 1,
                                "phenomenon_items": [],
                            },
                        ]
                    },
                }
            ],
            "meta": {
                "snapshot_id": f"snapshot-{tag}",
                "product_datetime": "2026-08-19T08:00:00+00:00",
                "generation_timestamp": "2026-08-19T08:00:45+00:00",
            },
        }
    }


def test_meteofrance_live_poll_uses_exact_endpoints_and_keeps_department_detail_raw_only():
    tag = uuid4().hex[:10]
    payload = _vigilance_payload(tag)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert str(request.url) == METEOFRANCE_TOKEN_ENDPOINT
            assert request.headers["authorization"] == "Basic test-application-id"
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(
                200,
                json={"access_token": "synthetic-access-token", "expires_in": 3600},
                request=request,
            )
        assert request.method == "GET"
        assert str(request.url) == METEOFRANCE_VIGILANCE_ENDPOINT
        assert request.headers["authorization"] == "Bearer synthetic-access-token"
        return httpx.Response(200, json=payload, request=request)

    network = httpx.Client(transport=httpx.MockTransport(handler))
    db = SessionLocal()
    try:
        events_before = db.query(HorizonGlobalEvent).count()
        candidates_before = db.query(HorizonEventCandidate).count()
        result = HorizonMeteoFranceService(db).poll("test-application-id", client=network)
        assert result["new_observations"] == 1
        assert result["replayed_observations"] == 0
        assert result["global_max_color_id"] == 3
        assert result["active_alert_count"] == 1
        assert result["official_primary"] is True
        assert result["candidates_created"] == 0
        assert result["promoted_events"] == 0

        source = db.query(HorizonSource).filter(
            HorizonSource.source_key == "meteofrance-vigilance"
        ).one()
        observation = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.external_key == f"meteofrance-vigilance:snapshot-{tag}",
        ).one()
        assert observation.geography == ["FR"]
        assert observation.observation_type == "official_weather_vigilance"
        assert observation.canonical_facts["global_max_color_id"] == 3
        assert len(observation.canonical_facts["alerts"]) == 1
        alert = observation.canonical_facts["alerts"][0]
        assert alert["domain_id"] == "75"
        assert alert["max_color_id"] == 3
        assert alert["phenomena"][0]["phenomenon_id"] == "6"

        # The raw official source does not skip the later normalization layer.
        assert db.query(HorizonGlobalEvent).count() == events_before
        assert db.query(HorizonEventCandidate).count() == candidates_before
        assert len(calls) == 2
    finally:
        db.close()
        network.close()


def test_meteofrance_snapshot_replay_is_idempotent():
    tag = uuid4().hex[:10]
    payload = _vigilance_payload(tag)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "token"}, request=request)
        return httpx.Response(200, json=payload, request=request)

    network = httpx.Client(transport=httpx.MockTransport(handler))
    db = SessionLocal()
    try:
        service = HorizonMeteoFranceService(db)
        first = service.poll("test-application-id", client=network)
        second = service.poll("test-application-id", client=network)
        assert first["new_observations"] == 1
        assert second["new_observations"] == 0
        assert second["replayed_observations"] == 1
        assert second["observation_id"] == first["observation_id"]
    finally:
        db.close()
        network.close()


def test_meteofrance_poll_fails_closed_on_auth_or_upstream_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid credential", request=request)

    network = httpx.Client(transport=httpx.MockTransport(handler))
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="Météo-France Vigilance poll failed"):
            HorizonMeteoFranceService(db).poll("bad-credential", client=network)
    finally:
        db.close()
        network.close()


def test_meteofrance_route_skips_cleanly_without_secret():
    previous = settings.meteofrance_application_id
    try:
        settings.meteofrance_application_id = ""
        response = api.post("/v1/horizon/live/meteofrance/poll")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["configured"] is False
        assert body["skipped"] is True
        assert body["new_observations"] == 0
    finally:
        settings.meteofrance_application_id = previous


def test_meteofrance_route_is_mounted_when_configured(monkeypatch):
    previous = settings.meteofrance_application_id

    def fake_poll(self, application_id, *, client=None):
        assert application_id == "synthetic-secret"
        return {
            "source_key": "meteofrance-vigilance",
            "configured": True,
            "new_observations": 1,
            "replayed_observations": 0,
            "observation_id": 123,
            "snapshot_id": "synthetic",
            "global_max_color_id": 3,
            "active_alert_count": 4,
            "official_primary": True,
            "candidates_created": 0,
            "promoted_events": 0,
            "detection_is_confirmation": False,
        }

    try:
        settings.meteofrance_application_id = "synthetic-secret"
        monkeypatch.setattr(HorizonMeteoFranceService, "poll", fake_poll)
        response = api.post("/v1/horizon/live/meteofrance/poll")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["configured"] is True
        assert body["official_primary"] is True
        assert body["promoted_events"] == 0
    finally:
        settings.meteofrance_application_id = previous
