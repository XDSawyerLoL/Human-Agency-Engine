from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_live_schemas import HorizonGdeltPollRequest
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from app.main import app
from app.services.horizon_live import GDELT_DOC_ENDPOINT, HorizonLiveService

api = TestClient(app)


def _article(tag: str) -> dict:
    return {
        "url": f"https://news.example.test/{tag}",
        "url_mobile": "",
        "title": "Fuel supply concerns rise after disruption",
        "seendate": "20260819T093000Z",
        "socialimage": "https://news.example.test/image.jpg",
        "domain": "news.example.test",
        "language": "English",
        "sourcecountry": "France",
    }


def test_live_gdelt_writes_raw_observation_only_and_recurring_poll_is_idempotent():
    tag = uuid4().hex[:12]
    article = _article(tag)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert str(request.url).startswith(GDELT_DOC_ENDPOINT)
        assert request.url.host == "api.gdeltproject.org"
        assert request.url.params["mode"] == "artlist"
        assert request.url.params["format"] == "json"
        assert request.url.params["timespan"] == "15min"
        return httpx.Response(200, json={"articles": [article]}, request=request)

    transport = httpx.MockTransport(handler)
    network = httpx.Client(transport=transport)
    db = SessionLocal()
    try:
        event_count_before = db.query(HorizonGlobalEvent).count()
        candidate_count_before = db.query(HorizonEventCandidate).count()
        service = HorizonLiveService(db)
        request = HorizonGdeltPollRequest(families=["supply"], max_records_per_query=5)

        first = service.poll_gdelt(request, client=network)
        assert first["new_observations"] == 1
        assert first["replayed_observations"] == 0
        assert first["promoted_events"] == 0
        assert first["candidates_created"] == 0
        assert first["detection_is_confirmation"] is False
        assert first["endpoint_allowlisted"] == GDELT_DOC_ENDPOINT

        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()
        row = db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.source_url == article["url"],
        ).one()
        assert row.observation_type == "news_report"
        assert row.geography == []
        assert row.canonical_facts["publisher_country"] == "France"
        assert row.canonical_facts["watch_family"] == "supply"

        second = service.poll_gdelt(request, client=network)
        assert second["new_observations"] == 0
        assert second["replayed_observations"] == 1
        assert db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.source_url == article["url"],
        ).count() == 1

        assert db.query(HorizonGlobalEvent).count() == event_count_before
        assert db.query(HorizonEventCandidate).count() == candidate_count_before
        assert len(calls) == 2
    finally:
        db.close()
        network.close()


def test_live_gdelt_partial_failure_is_visible_but_successful_families_are_kept():
    tag = uuid4().hex[:12]
    article = _article(tag)

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        if "blackout" in query:
            return httpx.Response(503, text="upstream unavailable", request=request)
        return httpx.Response(200, json={"articles": [article]}, request=request)

    network = httpx.Client(transport=httpx.MockTransport(handler))
    db = SessionLocal()
    try:
        result = HorizonLiveService(db).poll_gdelt(
            HorizonGdeltPollRequest(families=["supply", "infrastructure"]),
            client=network,
        )
        assert result["families_succeeded"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["family"] == "infrastructure"
        assert result["new_observations"] == 1
    finally:
        db.close()
        network.close()


def test_live_gdelt_fails_closed_when_every_discovery_query_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable", request=request)

    network = httpx.Client(transport=httpx.MockTransport(handler))
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="all GDELT live discovery queries failed"):
            HorizonLiveService(db).poll_gdelt(
                HorizonGdeltPollRequest(families=["supply", "public_health"]),
                client=network,
            )
    finally:
        db.close()
        network.close()


def test_live_gdelt_route_is_mounted_and_preserves_epistemic_boundary(monkeypatch):
    def fake_poll(self, request, *, client=None):
        return {
            "source_key": "gdelt-doc-2",
            "adapter": "gdelt_doc_json",
            "endpoint_allowlisted": GDELT_DOC_ENDPOINT,
            "families_requested": request.families or ["supply"],
            "families_succeeded": 1,
            "new_observations": 2,
            "replayed_observations": 0,
            "created_observation_ids": [1, 2],
            "errors": [],
            "promoted_events": 0,
            "candidates_created": 0,
            "detection_is_confirmation": False,
            "observed_at": "2026-08-19T09:30:00+00:00",
        }

    monkeypatch.setattr(HorizonLiveService, "poll_gdelt", fake_poll)
    response = api.post(
        "/v1/horizon/live/gdelt/poll",
        json={"families": ["supply"], "timespan_minutes": 15, "max_records_per_query": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_observations"] == 2
    assert body["promoted_events"] == 0
    assert body["candidates_created"] == 0
    assert body["detection_is_confirmation"] is False
