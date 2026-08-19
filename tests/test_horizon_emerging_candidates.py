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
            "Supply disruption raises shortage fears across distributors",
        ):
            _ingest(db, source, title=title, family="supply", observed_at=bucket_time)

        # Explicitly unrelated content in the same GDELT watch family must not be
        # coerced into a supply event merely because the discovery query returned it.
        _ingest(
            db,
            source,
            title="Company publishes quarterly logistics report",
            family="supply",
            observed_at=bucket_time,
        )
        # Current open bucket: must remain invisible until that bucket closes.
        _ingest(
            db,
            source,
            title="Fuel shortage reported in current open bucket",
            family="supply",
            observed_at=datetime(2030, 1, 1, 16, 48, 0),
        )

        result = HorizonEmergingService(db).cluster_gdelt(
            HorizonEmergingClusterRequest(
                bucket_minutes=15,
                lookback_buckets=4,
                min_articles=3,
            ),
            now=now,
        )
        assert result["candidate_count"] == 1
        assert result["candidates_are_confirmed_facts"] is False
        assert result["automatic_promotion_performed"] is False
        candidate_result = result["candidates"][0]
        assert candidate_result["event_type"] == "supply_disruption"
        assert candidate_result["article_count"] == 3
        assert candidate_result["fact_status"] == "unconfirmed_emerging_event"
        assert candidate_result["promotion_ready"] is False
        assert candidate_result["corroboration_score_is_probability"] is False

        candidate = db.query(HorizonEventCandidate).filter(
            HorizonEventCandidate.id == candidate_result["candidate_id"]
        ).one()
        assert candidate.promotion_status == "candidate"
        assert candidate.promoted_event_id is None
        assert candidate.normalized_facts["candidate_not_fact"] is True
        assert candidate.normalized_facts["raw_claims_verified"] is False
        assert candidate.normalized_facts["geography_status"] == "unknown"
        assert candidate.normalized_facts["article_count"] == 3

        replay = HorizonEmergingService(db).cluster_gdelt(
            HorizonEmergingClusterRequest(
                bucket_minutes=15,
                lookback_buckets=4,
                min_articles=3,
            ),
            now=now,
        )
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
            "Extreme heat threatens power demand this week",
            "Heatwave intensifies across the region",
            "Authorities prepare for extreme heat conditions",
        ):
            _ingest(db, source, title=title, family="weather_disaster", observed_at=closed)

        result = HorizonEmergingService(db).cluster_gdelt(
            HorizonEmergingClusterRequest(bucket_minutes=15, lookback_buckets=4, min_articles=3),
            now=now,
        )
        assert result["candidate_count"] == 1
        assert result["candidates"][0]["event_type"] == "extreme_heat"
        assert result["candidates"][0]["promotion_ready"] is False
    finally:
        db.close()


def test_emerging_cluster_route_is_mounted(monkeypatch):
    def fake_cluster(self, payload, *, now=None):
        return {
            "source_key": "gdelt-doc-2",
            "closed_bucket_end": "2030-01-01T12:00:00",
            "lookback_start": "2030-01-01T11:00:00",
            "raw_observations_scanned": 3,
            "ignored_unclassified": 0,
            "groups_below_threshold": 0,
            "candidates": [],
            "candidate_count": 0,
            "candidates_are_confirmed_facts": False,
            "automatic_promotion_performed": False,
        }

    monkeypatch.setattr(HorizonEmergingService, "cluster_gdelt", fake_cluster)
    response = api.post(
        "/v1/horizon/emerging/gdelt/cluster",
        json={"bucket_minutes": 15, "lookback_buckets": 4, "min_articles": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["candidates_are_confirmed_facts"] is False
