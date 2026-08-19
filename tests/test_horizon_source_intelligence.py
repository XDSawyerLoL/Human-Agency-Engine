from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _observation(source_key: str, external_key: str, *, title: str, source_url: str, facts: dict):
    return client.post(
        f"/v1/horizon/sources/{source_key}/observations",
        json={
            "external_key": external_key,
            "observation_type": "event_report",
            "title": title,
            "summary": "Synthetic source intelligence fixture.",
            "source_url": source_url,
            "geography": ["FR"],
            "canonical_facts": facts,
            "raw_metadata": {"synthetic": True},
            "event_time": "2026-08-19T06:00:00Z",
            "published_at": "2026-08-19T06:05:00Z",
            "observed_at": "2026-08-19T06:10:00Z",
        },
    )


def test_builtin_sources_encode_detection_vs_official_truth_roles():
    synced = client.post("/v1/horizon/sources/builtins/sync")
    assert synced.status_code == 200, synced.text
    by_key = {item["source_key"]: item for item in synced.json()["sources"]}
    assert by_key["gdelt-doc-2"]["source_class"] == "news_global"
    assert by_key["meteofrance-vigilance"]["source_class"] == "official_primary"
    assert by_key["meteofrance-vigilance"]["requires_credentials"] is True

    listed = client.get("/v1/horizon/sources")
    assert listed.status_code == 200
    source_map = {item["source_key"]: item for item in listed.json()}
    assert source_map["gdelt-doc-2"]["trust_weight_is_probability"] is False
    assert source_map["gdelt-doc-2"]["metadata"]["role"] == "broad_detection_not_ground_truth"
    assert source_map["meteofrance-vigilance"]["metadata"]["role"] == "official_weather_warning"


def test_raw_observation_is_idempotent_but_payload_rewrite_is_rejected():
    client.post("/v1/horizon/sources/builtins/sync")
    key = f"gdelt-{uuid4().hex[:10]}"
    first = _observation(
        "gdelt-doc-2",
        key,
        title="Heat coverage accelerates",
        source_url="https://example.invalid/a",
        facts={"topic": "heat"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True

    replay = _observation(
        "gdelt-doc-2",
        key,
        title="Heat coverage accelerates",
        source_url="https://example.invalid/a",
        facts={"topic": "heat"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["id"] == first.json()["id"]

    rewritten = _observation(
        "gdelt-doc-2",
        key,
        title="Rewritten history",
        source_url="https://example.invalid/b",
        facts={"topic": "different"},
    )
    assert rewritten.status_code == 409
    assert "immutable payload" in rewritten.text.lower()


def test_news_only_candidate_cannot_be_promoted_as_confirmed_event():
    client.post("/v1/horizon/sources/builtins/sync")
    key = f"news-{uuid4().hex[:10]}"
    observation = _observation(
        "gdelt-doc-2",
        key,
        title="Possible supply disruption",
        source_url="https://example.invalid/news",
        facts={"reported_disruption": True},
    )
    assert observation.status_code == 200, observation.text
    candidate = client.post(
        "/v1/horizon/sources/candidates",
        json={
            "observation_ids": [observation.json()["id"]],
            "event_type": "supply_disruption",
            "title": "Possible supply disruption",
            "geography": ["FR"],
        },
    )
    assert candidate.status_code == 200, candidate.text
    body = candidate.json()
    assert body["promotion_readiness"]["ready"] is False
    assert body["corroboration_score_is_probability"] is False

    promoted = client.post(f"/v1/horizon/sources/candidates/{body['id']}/promote")
    assert promoted.status_code == 409


def test_official_primary_observation_can_promote_with_full_provenance():
    client.post("/v1/horizon/sources/builtins/sync")
    tag = uuid4().hex[:10]
    official = _observation(
        "meteofrance-vigilance",
        f"mf-{tag}",
        title="Official heat vigilance",
        source_url="https://example.invalid/meteo",
        facts={"vigilance_level": "orange", "phenomenon": "heat"},
    )
    assert official.status_code == 200, official.text
    candidate = client.post(
        "/v1/horizon/sources/candidates",
        json={
            "observation_ids": [official.json()["id"]],
            "event_type": "extreme_heat",
            "title": "Official heat vigilance",
            "geography": ["FR"],
        },
    )
    assert candidate.status_code == 200, candidate.text
    assert candidate.json()["promotion_readiness"]["official_primary_present"] is True
    assert candidate.json()["promotion_readiness"]["ready"] is True

    promoted = client.post(f"/v1/horizon/sources/candidates/{candidate.json()['id']}/promote")
    assert promoted.status_code == 200, promoted.text
    event = promoted.json()
    assert event["source"] == "meteofrance-vigilance"
    assert event["raw_facts"]["canonical_facts"]["phenomenon"] == "heat"
    assert event["raw_facts"]["corroboration"]["corroboration_score_is_probability"] is False
