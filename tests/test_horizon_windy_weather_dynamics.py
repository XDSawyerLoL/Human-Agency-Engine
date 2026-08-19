from datetime import datetime, timedelta, timezone
import json

import httpx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_source_models import HorizonEventCandidate, HorizonSource
from app.horizon_windy_schemas import HorizonWindyPollRequest
from app.main import app
from app.services.horizon_windy import HorizonWindyService, WINDY_POINT_FORECAST_ENDPOINT


client = TestClient(app)


def _payload(peak_c: float, peak_offset_hours: int) -> dict:
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    ts = [int((base + timedelta(hours=hour)).timestamp() * 1000) for hour in (3, 6, 9, 12, 15, 18)]
    temps = [300.15, 302.15, 304.15, 305.15, 303.15, 301.15]
    index = min(range(len(ts)), key=lambda idx: abs((ts[idx] / 1000) - (base + timedelta(hours=peak_offset_hours)).timestamp()))
    temps[index] = peak_c + 273.15
    return {
        "ts": ts,
        "units": {"temp-surface": "K", "gust-surface": "m/s", "past3hprecip-surface": "mm"},
        "temp-surface": temps,
        "gust-surface": [4, 5, 6, 7, 6, 5],
        "past3hprecip-surface": [0, 0, 0, 0, 0, 0],
    }


def test_windy_multi_model_heat_consensus_creates_unconfirmed_candidate_only():
    db = SessionLocal()
    observed = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    model_payloads = {
        "aromeFrance": _payload(35.0, 12),
        "iconEu": _payload(34.0, 12),
        "gfs": _payload(33.5, 15),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == WINDY_POINT_FORECAST_ENDPOINT
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=model_payloads[body["model"]], request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = HorizonWindyService(db).poll(
            HorizonWindyPollRequest(
                lat=48.8566,
                lon=2.3522,
                geography=["FR", "75"],
                horizon_hours=48,
                heat_watch_threshold_c=32,
                max_heat_model_spread_c=5,
            ),
            "professional-test-fixture-key",
            client=mock,
            observed_at=observed,
        )
        assert result["models_succeeded"] == 3
        assert result["candidate_id"] is not None
        assert result["heat_consensus"]["supporting_model_count"] == 3
        assert result["critical_semantics"]["windy_is_official_confirmation"] is False
        assert result["critical_semantics"]["candidate_auto_promoted"] is False
        assert result["critical_semantics"]["model_consensus_is_probability"] is False

        candidate = db.query(HorizonEventCandidate).filter(
            HorizonEventCandidate.id == result["candidate_id"]
        ).one()
        assert candidate.event_type == "extreme_heat"
        assert candidate.promotion_status == "candidate"
        assert candidate.promoted_event_id is None
        assert candidate.normalized_facts["forecast_only"] is True

        source = db.query(HorizonSource).filter(HorizonSource.source_key == "windy-point-forecast").one()
        assert source.source_class == "model_forecast"
        assert source.metadata_json["historical_forecast_api_available"] is False
    finally:
        mock.close()
        db.close()


def test_windy_divergent_hot_models_do_not_create_heat_candidate():
    db = SessionLocal()
    observed = datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc)
    model_payloads = {
        "aromeFrance": _payload(40.0, 12),
        "iconEu": _payload(33.0, 12),
        "gfs": _payload(32.5, 15),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=model_payloads[body["model"]], request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = HorizonWindyService(db).poll(
            HorizonWindyPollRequest(
                lat=43.6047,
                lon=1.4442,
                geography=["FR", "31"],
                horizon_hours=48,
                heat_watch_threshold_c=32,
                max_heat_model_spread_c=5,
            ),
            "professional-test-fixture-key",
            client=mock,
            observed_at=observed,
        )
        assert result["heat_consensus"] is not None
        assert result["heat_consensus"]["peak_temp_spread_c"] > 5
        assert result["candidate_id"] is None
    finally:
        mock.close()
        db.close()


def test_windy_route_is_mounted_and_missing_secret_fails_closed():
    response = client.post(
        "/v1/horizon/live/windy/poll",
        json={"lat": 48.8566, "lon": 2.3522},
    )
    assert response.status_code == 400, response.text
    assert "WINDY_POINT_FORECAST_API_KEY" in response.text
