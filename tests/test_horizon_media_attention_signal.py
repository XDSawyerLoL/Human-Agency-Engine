from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_behavioral_signal_schemas import HorizonMediaAttentionRefreshRequest
from app.horizon_models import HorizonSocialSignal
from app.main import app
from app.services.horizon_media_attention import HorizonMediaAttentionService

api = TestClient(app)


def _event(tag: str) -> int:
    response = api.post(
        "/v1/horizon/events",
        json={
            "event_key": f"media-heat-{tag}",
            "event_type": "extreme_heat",
            "title": "Official extreme heat alert",
            "summary": "Synthetic heat event.",
            "geography": ["FR"],
            "source": "synthetic-official-primary",
            "source_url": "https://example.invalid/heat",
            "source_reliability": 0.95,
            "raw_facts": {"fact_only": True},
            "occurred_at": "2026-08-19T06:00:00Z",
            "first_observed_at": "2026-08-19T06:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _timeline(*, spike: bool) -> dict:
    start = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)
    data = []
    for index in range(12):
        recent = index >= 8
        count = 40 if spike and recent else 10
        at = start + timedelta(minutes=15 * index)
        data.append(
            {
                "date": at.strftime("%Y%m%dT%H%M%SZ"),
                "value": count,
                "norm": 10000,
            }
        )
    return {"timeline": [{"series": "Volume", "data": data}]}


def _client(payload: dict, calls: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        assert request.url.host == "api.gdeltproject.org"
        assert request.url.params["mode"] == "timelinevolraw"
        assert request.url.params["format"] == "json"
        assert request.url.params["timespan"] == "24h"
        assert "heatwave" in request.url.params["query"]
        assert "France" in request.url.params["query"]
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_stable_media_volume_creates_no_behavioral_signal():
    event_id = _event(uuid4().hex[:10])
    network = _client(_timeline(spike=False))
    db = SessionLocal()
    try:
        result = HorizonMediaAttentionService(db).refresh(
            HorizonMediaAttentionRefreshRequest(event_ids=[event_id]),
            client=network,
        )
        assert result["signals_created"] == 0
        assert result["formal_probability"] is False
        diagnostic = result["diagnostics"][0]
        assert diagnostic["status"] == "below_signal_threshold"
        assert round(diagnostic["attention_ratio"], 6) == 1.0
        assert diagnostic["attention_ratio_is_probability"] is False
        assert db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id == event_id,
            HorizonSocialSignal.signal_type == "media_attention",
        ).count() == 0
    finally:
        db.close()
        network.close()


def test_media_attention_spike_is_normalized_idempotent_and_advances_only_first_heat_stage():
    tag = uuid4().hex[:10]
    event_id = _event(tag)
    calls = []
    network = _client(_timeline(spike=True), calls)
    db = SessionLocal()
    try:
        service = HorizonMediaAttentionService(db)
        request = HorizonMediaAttentionRefreshRequest(event_ids=[event_id])
        first = service.refresh(request, client=network)
        assert first["signals_created"] == 1
        assert first["signal_semantics"] == "media_attention_acceleration_only"
        diagnostic = first["diagnostics"][0]
        assert diagnostic["status"] == "signal_created"
        assert round(diagnostic["attention_ratio"], 6) == 4.0

        signal = db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.id == first["created_signal_ids"][0]
        ).one()
        assert signal.signal_type == "media_attention"
        assert signal.direction == "up"
        assert signal.normalized_score > 0
        assert signal.reliability <= 0.55
        assert signal.evidence["metric"] == "share_of_gdelt_monitored_coverage"
        assert signal.evidence["ratio_is_probability"] is False
        assert "purchase_behavior" in signal.evidence["does_not_measure"]

        second = service.refresh(request, client=network)
        assert second["signals_created"] == 0
        assert second["signals_replayed"] == 1
        assert db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id == event_id,
            HorizonSocialSignal.signal_type == "media_attention",
        ).count() == 1
        assert len(calls) == 2
    finally:
        db.close()
        network.close()

    library = api.post("/v1/horizon/response-library/builtins/sync")
    assert library.status_code == 200, library.text
    heat = next(
        item
        for item in library.json()["patterns"]
        if item["pattern_key"] == "builtin-extreme-heat-cooling-demand-v1"
    )
    cascade = api.post(
        "/v1/horizon/cascades/project",
        json={
            "event_id": event_id,
            "pattern_id": heat["id"],
            "as_of": "2026-08-19T07:00:00Z",
            "mode": "backtest",
        },
    )
    assert cascade.status_code == 200, cascade.text
    body = cascade.json()
    assert body["current_stage"] == "heat threat perception"
    assert body["next_stage"] == "cooling search acceleration"
    assert body["stages"][1]["state"] == "latent"
    assert body["probability_basis"] == "not_calibrated"


def test_media_attention_route_is_mounted_without_changing_signal_semantics(monkeypatch):
    def fake_refresh(self, request, *, client=None):
        return {
            "engine": "horizon-gdelt-media-attention-v0.1",
            "events_scanned": 1,
            "signals_created": 1,
            "signals_replayed": 0,
            "created_signal_ids": [123],
            "diagnostics": [],
            "signal_semantics": "media_attention_acceleration_only",
            "formal_probability": False,
        }

    monkeypatch.setattr(HorizonMediaAttentionService, "refresh", fake_refresh)
    response = api.post(
        "/v1/horizon/signals/media-attention/refresh",
        json={"event_ids": [1]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["signals_created"] == 1
    assert body["signal_semantics"] == "media_attention_acceleration_only"
    assert body["formal_probability"] is False
