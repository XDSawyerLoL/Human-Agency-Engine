from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_source_models import HorizonEventCandidate
from app.main import app

client = TestClient(app)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _create_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "country": "FR",
            "currency": "EUR",
            "timezone": "Europe/Paris",
        },
    )
    assert response.status_code == 200, response.text


def _set_department(uid: str, code: str):
    response = client.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "location",
            "key": "department",
            "value": {"code": code},
            "source": "user",
            "confidence": 1.0,
            "sensitivity": "personal",
            "observed_at": "2026-08-18T10:00:00Z",
        },
    )
    assert response.status_code == 200, response.text


def _official_heat_observation(tag: str) -> int:
    synced = client.post("/v1/horizon/sources/builtins/sync")
    assert synced.status_code == 200, synced.text
    response = client.post(
        "/v1/horizon/sources/meteofrance-vigilance/observations",
        json={
            "external_key": f"scope-meteofrance-{tag}",
            "observation_type": "official_weather_vigilance",
            "title": "Météo-France Vigilance nationale niveau 3",
            "summary": "Vigilance orange canicule synthétique pour test.",
            "source_url": "https://vigilance.meteofrance.fr/fr",
            "geography": ["FR"],
            "canonical_facts": {
                "snapshot_id": f"scope-snapshot-{tag}",
                "product_datetime": "2026-08-19T08:00:00+00:00",
                "generation_timestamp": "2026-08-19T08:00:45+00:00",
                "global_max_color_id": 3,
                "alerts": [
                    {
                        "echeance": "J",
                        "begin_validity_time": "2026-08-19T08:00:00Z",
                        "end_validity_time": "2026-08-19T23:00:00Z",
                        "domain_id": "75",
                        "max_color_id": 3,
                        "phenomena": [
                            {
                                "phenomenon_id": "6",
                                "max_color_id": 3,
                                "timelaps": [
                                    {
                                        "begin_time": "2026-08-19T10:00:00Z",
                                        "end_time": "2026-08-19T20:00:00Z",
                                        "color_id": 3,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "raw_metadata": {"fixture": True},
            "event_time": "2026-08-19T08:00:00Z",
            "published_at": "2026-08-19T08:00:45Z",
            "observed_at": "2026-08-19T08:01:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _heat_pattern(tag: str) -> int:
    response = client.post(
        "/v1/horizon/patterns",
        json={
            "pattern_key": f"scope-heat-pattern-{tag}",
            "name": "Extreme heat collective response",
            "event_types": ["extreme_heat"],
            "required_signal_types": [],
            "predicted_response": "Heat exposure and cooling demand may increase.",
            "mechanism_chain": [
                "heat threat perception",
                "cooling search acceleration",
                "purchase acceleration",
            ],
            "expected_lag_hours_low": 0,
            "expected_lag_hours_high": 48,
            "confidence": 0.9,
            "support_count": 10,
            "contradiction_count": 1,
            "provenance": {"fixture": True},
            "knowledge_available_at": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_meteofrance_normalization_preserves_raw_facts_and_creates_scoped_confirmed_event():
    tag = uuid4().hex[:10]
    observation_id = _official_heat_observation(tag)

    normalized = client.post(f"/v1/horizon/normalize/meteofrance/{observation_id}")
    assert normalized.status_code == 200, normalized.text
    body = normalized.json()
    assert body["normalized_event_count"] == 1
    assert body["scope_preserved"] is True
    event = body["events"][0]
    assert event["event_type"] == "extreme_heat"
    assert event["phenomenon_id"] == "6"
    assert event["phenomenon_name"] == "canicule"
    assert event["color_name"] == "orange"
    assert event["domain_id"] == "75"
    assert event["personal_scope"]["all"][0]["state_key"] == "location.department"
    assert event["personal_scope"]["all"][0]["value"] == "75"
    assert event["official_primary_promoted"] is True

    events = client.get("/v1/horizon/events")
    assert events.status_code == 200
    promoted = next(item for item in events.json() if item["id"] == event["event_id"])
    assert promoted["source"] == "meteofrance-vigilance"

    db = SessionLocal()
    try:
        candidate = db.query(HorizonEventCandidate).filter(
            HorizonEventCandidate.id == event["candidate_id"]
        ).one()
        assert candidate.normalizer_version == "meteofrance-v6-personal-scope-v0.1"
        assert candidate.normalized_facts["personal_scope"]["all"][0]["value"] == "75"
    finally:
        db.close()

    # Re-normalization is deterministic/idempotent.
    again = client.post(f"/v1/horizon/normalize/meteofrance/{observation_id}")
    assert again.status_code == 200
    assert again.json()["events"][0]["event_id"] == event["event_id"]


def test_personal_scope_is_hard_gate_for_impact_and_missing_location_cannot_be_urgent():
    tag = uuid4().hex[:10]
    observation_id = _official_heat_observation(tag)
    normalized = client.post(f"/v1/horizon/normalize/meteofrance/{observation_id}").json()
    event_id = normalized["events"][0]["event_id"]
    pattern_id = _heat_pattern(tag)

    local_user = _uid("scope-local")
    remote_user = _uid("scope-remote")
    unknown_user = _uid("scope-unknown")
    for uid in (local_user, remote_user, unknown_user):
        _create_user(uid)
    _set_department(local_user, "75")
    _set_department(remote_user, "29")

    payload = {
        "event_id": event_id,
        "pattern_id": pattern_id,
        "as_of": "2026-08-19T09:00:00Z",
        "mode": "backtest",
    }
    local = client.post(f"/v1/horizon/impact/users/{local_user}/assess", json=payload)
    remote = client.post(f"/v1/horizon/impact/users/{remote_user}/assess", json=payload)
    unknown = client.post(f"/v1/horizon/impact/users/{unknown_user}/assess", json=payload)
    assert local.status_code == 200, local.text
    assert remote.status_code == 200, remote.text
    assert unknown.status_code == 200, unknown.text

    local_assessment = local.json()["assessment"]
    remote_assessment = remote.json()["assessment"]
    unknown_assessment = unknown.json()["assessment"]

    assert local_assessment["personal_exposure_layer"]["personal_scope"]["status"] == "matched"
    assert local_assessment["attention_score"] > 0

    assert remote_assessment["personal_exposure_layer"]["personal_scope"]["status"] == "mismatched"
    assert remote_assessment["attention_score"] == 0.0
    assert remote_assessment["attention_band"] == "silent"
    assert remote_assessment["explanation"]["should_surface"] is False

    assert unknown_assessment["personal_exposure_layer"]["personal_scope"]["status"] == "unknown"
    assert unknown_assessment["attention_score"] <= 0.49
    assert unknown_assessment["attention_band"] in {"silent", "watch"}
    assert unknown_assessment["explanation"]["missing_personal_state_for_scope"] is True
