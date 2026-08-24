from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_emerging_schemas import HorizonEmergingClusterRequest
from app.horizon_source_models import HorizonEventCandidate, HorizonSource
from app.horizon_source_schemas import HorizonObservationIngest
from app.main import app
from app.services.horizon_emerging import HorizonEmergingService
from app.services.horizon_sources import HorizonSourceService

api = TestClient(app)


def _ingest(db, source, *, title: str, family: str, observed_at: datetime):
    suffix = uuid4().hex
    return HorizonSourceService(db).ingest_observation(
        source,
        HorizonObservationIngest(
            external_key=f"emerging-test-{suffix}",
            observation_type="news_report",
            title=title,
            summary="",
            source_url=f"https://example.test/{suffix}",
            geography=[],
            canonical_facts={
                "watch_family": family,
                "publisher_domain": "example.test",
                "publisher_country": "US",
            },
            raw_metadata={"fixture": True},
            event_time=None,
            published_at=observed_at - timedelta(minutes=2),
            observed_at=observed_at,
        ),
    )[0]


def _cluster(db, now: datetime, min_articles: int = 3):
    return HorizonEmergingService(db).cluster_gdelt(
        HorizonEmergingClusterRequest(bucket_minutes=15, lookback_buckets=4, min_articles=min_articles),
        now=now,
    )


def test_closed_gdelt_bucket_creates_unconfirmed_supply_candidate_but_never_promotes_single_source_repetition():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()
        now = datetime(2030, 1, 1, 16, 52, 0)
        bucket_time = datetime(2030, 1, 1, 16, 34, 0)
        for title in (
            "Fuel shortage expands as deliveries are delayed",
            "Regional fuel shortage prompts new supply concerns",
            "Fuel supply disruption raises shortage fears across distributors",
        ):
            _ingest(db, source, title=title, family="supply", observed_at=bucket_time)

        _ingest(db, source, title="Company publishes quarterly logistics report", family="supply", observed_at=bucket_time)
        _ingest(
            db,
            source,
            title="Fuel shortage reported in current open bucket",
            family="supply",
            observed_at=datetime(2030, 1, 1, 16, 48, 0),
        )

        result = _cluster(db, now)
        assert result["candidate_count"] == 1
        assert result["candidates_are_confirmed_facts"] is False
        assert result["automatic_promotion_performed"] is False
        assert result["single_source_repetition_can_confirm_fact"] is False
        candidate_result = result["candidates"][0]
        assert candidate_result["event_type"] == "supply_disruption"
        assert candidate_result["article_count"] == 3
        assert "fuel" in candidate_result["cluster_anchor_tokens"]
        assert candidate_result["fact_status"] == "unconfirmed_emerging_event"
        assert candidate_result["promotion_ready"] is False
        assert candidate_result["corroboration_score_is_probability"] is False

        candidate = db.query(HorizonEventCandidate).filter(HorizonEventCandidate.id == candidate_result["candidate_id"]).one()
        assert candidate.promotion_status == "candidate"
        assert candidate.promoted_event_id is None
        assert candidate.normalized_facts["candidate_not_fact"] is True
        assert candidate.normalized_facts["raw_claims_verified"] is False
        assert candidate.normalized_facts["geography_status"] == "unknown"
        assert candidate.normalized_facts["article_count"] == 3
        assert candidate.normalized_facts["episode_clustering_required"] is True

        replay = _cluster(db, now)
        assert replay["candidate_count"] == 1
        assert replay["candidates"][0]["candidate_id"] == candidate.id
    finally:
        db.close()


def test_explicit_heat_language_can_create_extreme_heat_hypothesis_while_weak_cluster_stays_below_threshold():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()
        now = datetime(2031, 7, 1, 12, 7, 0)
        closed = datetime(2031, 7, 1, 11, 49, 0)
        for title in (
            "Extreme heat threatens power demand in France",
            "Heatwave intensifies across France",
            "Authorities prepare France for extreme heat conditions",
        ):
            _ingest(db, source, title=title, family="weather_disaster", observed_at=closed)

        result = _cluster(db, now)
        assert result["candidate_count"] == 1
        assert result["candidates"][0]["event_type"] == "extreme_heat"
        assert "france" in result["candidates"][0]["cluster_anchor_tokens"]
        assert result["candidates"][0]["promotion_ready"] is False
    finally:
        db.close()


def test_world_discovery_classifies_economy_conflict_health_cyber_policy_finance_and_energy_without_confirming_them():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()
        now = datetime(2034, 2, 1, 10, 7, 0)
        closed = datetime(2034, 2, 1, 9, 49, 0)
        fixtures = {
            "economy_labor": ("mass_layoff", [
                "Acme mass layoffs affect European offices",
                "Acme layoffs expand after weak demand",
                "Acme announces another round of layoffs",
            ]),
            "social_collective": ("mass_protest", [
                "Aurora mass protest fills central district",
                "Aurora demonstrations expand across downtown",
                "Aurora protests draw another large crowd",
            ]),
            "conflict_security": ("economic_sanctions", [
                "Orion sanctions package announced by allies",
                "New sanctions target Orion exports",
                "Orion faces expanded economic sanctions",
            ]),
            "public_health": ("public_health_outbreak", [
                "Nova disease outbreak prompts surveillance",
                "Nova outbreak expands across districts",
                "Health agency tracks Nova epidemic outbreak",
            ]),
            "cyber_technology": ("cyber_incident", [
                "Atlas ransomware cyber attack disrupts services",
                "Atlas hit by ransomware campaign",
                "Atlas cyber incident linked to ransomware",
            ]),
            "regulation_policy": ("trade_policy_change", [
                "Helios export ban changes trade flows",
                "Helios products face new export ban",
                "Government expands Helios export ban",
            ]),
            "financial_stress": ("financial_stress", [
                "Meridian bank run triggers liquidity concerns",
                "Meridian faces accelerating bank run",
                "Regulators respond to Meridian bank run",
            ]),
            "energy_markets": ("energy_market_stress", [
                "NorthSea energy price spike hits industry",
                "NorthSea energy crisis drives price spike",
                "NorthSea markets react to energy price spike",
            ]),
        }
        for family, (_, titles) in fixtures.items():
            for title in titles:
                _ingest(db, source, title=title, family=family, observed_at=closed)

        result = _cluster(db, now)
        types = {item["event_type"] for item in result["candidates"]}
        assert {expected for expected, _ in fixtures.values()}.issubset(types)
        assert all(item["promotion_ready"] is False for item in result["candidates"])
        assert result["automatic_promotion_performed"] is False
    finally:
        db.close()


def test_unrelated_same_type_stories_do_not_merge_into_false_episode():
    db = SessionLocal()
    try:
        HorizonSourceService(db).sync_builtin_sources()
        source = db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()
        now = datetime(2035, 1, 1, 12, 7, 0)
        closed = datetime(2035, 1, 1, 11, 49, 0)
        for title in (
            "Acme mass layoffs affect Paris unit",
            "Acme layoffs continue after restructuring",
            "Beta mass layoffs affect Madrid unit",
            "Beta layoffs continue after restructuring",
        ):
            _ingest(db, source, title=title, family="economy_labor", observed_at=closed)

        result = _cluster(db, now, min_articles=3)
        assert not any(item["event_type"] == "mass_layoff" for item in result["candidates"])
        assert result["groups_below_threshold"] >= 2
    finally:
        db.close()


def test_emerging_cluster_route_is_mounted(monkeypatch):
    def fake_cluster(self, payload, *, now=None):
        return {
            "source_key": "gdelt-doc-2",
            "normalizer_version": "gdelt-emerging-cluster-v0.2-world",
            "closed_bucket_end": "2030-01-01T12:00:00",
            "lookback_start": "2030-01-01T11:00:00",
            "raw_observations_scanned": 3,
            "ignored_unclassified": 0,
            "episode_groups_considered": 0,
            "groups_below_threshold": 0,
            "candidates": [],
            "candidate_count": 0,
            "candidate_event_types": [],
            "candidates_are_confirmed_facts": False,
            "automatic_promotion_performed": False,
            "single_source_repetition_can_confirm_fact": False,
        }

    monkeypatch.setattr(HorizonEmergingService, "cluster_gdelt", fake_cluster)
    response = api.post(
        "/v1/horizon/emerging/gdelt/cluster",
        json={"bucket_minutes": 15, "lookback_buckets": 4, "min_articles": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["candidates_are_confirmed_facts"] is False
