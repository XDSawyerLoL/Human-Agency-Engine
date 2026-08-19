from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from app.main import app
from app.services.horizon_event_graph import HorizonEventGraphService
from app.services.horizon_sources import HorizonSourceService


client = TestClient(app)


def _event(db, *, key: str, event_type: str, title: str, source: str, geography: list[str], at: datetime):
    row = HorizonGlobalEvent(
        event_key=key,
        event_type=event_type,
        title=title,
        summary="event graph fixture",
        geography=geography,
        source=source,
        source_url="https://example.invalid/event",
        source_reliability=0.95,
        raw_facts={},
        occurred_at=at,
        first_observed_at=at,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _meteoalarm_candidate(db, *, tag: str, at: datetime):
    service = HorizonSourceService(db)
    source = service.upsert_source(
        HorizonSourceUpsert(
            source_key="meteoalarm:france",
            name="MeteoAlarm France event graph fixture",
            source_class="official_aggregator",
            adapter_kind="meteoalarm_atom_warning_feed",
            domains=["weather"],
            geography=["FR"],
            trust_weight=0.93,
            refresh_seconds=600,
            requires_credentials=False,
            enabled=True,
            metadata_json={
                "evidence_roles": ["confirmation", "physical_state"],
                "independence_family": "weather-warning:france",
            },
        )
    )
    observation, _ = service.ingest_observation(
        source,
        HorizonObservationIngest(
            external_key=f"meteoalarm-graph-{tag}",
            observation_type="official_weather_warning_aggregated_snapshot",
            title="Orange heat warning Ile-de-France",
            summary="Heat warning relay fixture.",
            source_url="https://example.invalid/meteoalarm",
            geography=["FR", "75"],
            canonical_facts={"event": "Extreme high temperature"},
            raw_metadata={"fixture": True},
            event_time=at + timedelta(hours=2),
            published_at=at,
            observed_at=at,
        ),
    )
    return service.build_candidate(
        HorizonCandidateBuild(
            observation_ids=[observation.id],
            event_type="extreme_heat",
            title="Orange heat warning Ile-de-France",
            geography=["FR", "75"],
            normalized_facts={
                "provider": "MeteoAlarm",
                "effective_at": (at + timedelta(hours=2)).isoformat(),
                "expires_at": (at + timedelta(hours=30)).isoformat(),
                "country_iso2": "FR",
                "area": "Ile-de-France",
            },
            normalizer_version="graph-fixture-v1",
        )
    )


def test_event_graph_clusters_cross_source_same_episode_and_attached_signal_without_promoting_candidate():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2031, 1, 1, 6, 0, 0)
    try:
        HorizonSourceService(db).sync_builtin_sources()
        official = _event(
            db,
            key=f"graph-heat-{tag}",
            event_type="extreme_heat",
            title="Vigilance orange canicule Paris",
            source="meteofrance-vigilance",
            geography=["FR", "75"],
            at=base + timedelta(hours=1),
        )
        candidate = _meteoalarm_candidate(db, tag=tag, at=base)
        signal = HorizonSocialSignal(
            event_id=official.id,
            signal_key=f"graph-rte-{tag}",
            signal_type="cooling_load_pressure_live",
            source="rte-eco2mix-regional-tr",
            geography=["FR", "REGION:11"],
            value=1100,
            baseline=1000,
            normalized_score=1.7,
            direction="up",
            reliability=0.82,
            evidence={"final_materialization_label": False},
            observed_at=base + timedelta(hours=4),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)

        result = HorizonEventGraphService(db).build(
            HorizonEventGraphBuildRequest(
                as_of=base + timedelta(hours=6),
                lookback_hours=48,
                max_events=100,
                max_candidates=100,
                max_signals=100,
            )
        )
        graph = result["graph_snapshot"]
        node_keys = {node["key"] for node in graph["nodes"]}
        assert f"event:{official.id}" in node_keys
        assert f"candidate:{candidate.id}" in node_keys
        assert f"signal:{signal.id}" in node_keys

        same = [edge for edge in graph["edges"] if edge["relation"] == "same_episode_support"]
        assert any({edge["left"], edge["right"]} == {f"event:{official.id}", f"candidate:{candidate.id}"} for edge in same)
        attachment = [edge for edge in graph["edges"] if edge["relation"] == "observed_signal_attachment"]
        assert any(edge["left"] == f"event:{official.id}" and edge["right"] == f"signal:{signal.id}" for edge in attachment)
        episode = next(item for item in graph["episodes"] if f"event:{official.id}" in item["member_keys"])
        assert f"candidate:{candidate.id}" in episode["member_keys"]
        assert f"signal:{signal.id}" in episode["member_keys"]
        assert episode["contains_unconfirmed_candidate"] is True
        assert candidate.promoted_event_id is None
        assert candidate.promotion_status == "candidate"
        assert graph["critical_semantics"]["unconfirmed_candidates_remain_unconfirmed"] is True
        assert graph["critical_semantics"]["same_episode_score_is_probability"] is False
    finally:
        db.close()


def test_plausible_dependency_never_merges_two_episodes_or_asserts_causality():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2032, 1, 1, 7, 0, 0)
    try:
        flood = _event(
            db,
            key=f"graph-flood-{tag}",
            event_type="flood",
            title="Flood warning France",
            source="gdacs-official",
            geography=["FR"],
            at=base,
        )
        rail = _event(
            db,
            key=f"graph-rail-{tag}",
            event_type="rail_transport_disruption",
            title="Rail service interrupted France",
            source="sncf-service-alerts",
            geography=["FR"],
            at=base + timedelta(hours=8),
        )
        result = HorizonEventGraphService(db).build(
            HorizonEventGraphBuildRequest(
                as_of=base + timedelta(hours=12),
                lookback_hours=48,
                max_events=100,
                max_candidates=100,
                max_signals=100,
            )
        )
        graph = result["graph_snapshot"]
        dependency = next(
            edge for edge in graph["edges"]
            if edge["relation"] == "plausible_downstream_dependency"
            and edge["left"] == f"event:{flood.id}"
            and edge["right"] == f"event:{rail.id}"
        )
        assert dependency["asserted_causality"] is False
        assert dependency["diagnostic_score_is_probability"] is False
        assert dependency["evidence"]["causal_claim"] is False
        assert not any(
            f"event:{flood.id}" in episode["member_keys"] and f"event:{rail.id}" in episode["member_keys"]
            for episode in graph["episodes"]
        )
    finally:
        db.close()


def test_event_graph_is_evidence_idempotent_and_respects_cutoff_for_future_signal():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2033, 1, 1, 8, 0, 0)
    try:
        event = _event(
            db,
            key=f"graph-cutoff-{tag}",
            event_type="extreme_heat",
            title="Heat event cutoff fixture",
            source="meteofrance-vigilance",
            geography=["FR", "75"],
            at=base,
        )
        future_signal = HorizonSocialSignal(
            event_id=event.id,
            signal_key=f"graph-future-{tag}",
            signal_type="cooling_load_pressure_live",
            source="rte-eco2mix-regional-tr",
            geography=["FR", "REGION:11"],
            value=1100,
            baseline=1000,
            normalized_score=1.5,
            direction="up",
            reliability=0.82,
            evidence={"fixture": True},
            observed_at=base + timedelta(hours=10),
        )
        db.add(future_signal)
        db.commit()
        db.refresh(future_signal)

        service = HorizonEventGraphService(db)
        first = service.build(HorizonEventGraphBuildRequest(
            as_of=base + timedelta(hours=5), lookback_hours=48, max_events=100, max_candidates=100, max_signals=100
        ))
        assert f"signal:{future_signal.id}" not in {node["key"] for node in first["graph_snapshot"]["nodes"]}

        unchanged = service.build(HorizonEventGraphBuildRequest(
            as_of=base + timedelta(hours=6), lookback_hours=48, max_events=100, max_candidates=100, max_signals=100
        ))
        assert unchanged["id"] == first["id"]
        assert unchanged["replayed_existing_snapshot"] is True

        changed = service.build(HorizonEventGraphBuildRequest(
            as_of=base + timedelta(hours=12), lookback_hours=48, max_events=100, max_candidates=100, max_signals=100
        ))
        assert changed["id"] != first["id"]
        assert f"signal:{future_signal.id}" in {node["key"] for node in changed["graph_snapshot"]["nodes"]}
        assert changed["graph_snapshot"]["critical_semantics"]["evidence_after_cutoff_excluded"] is True
    finally:
        db.close()


def test_event_graph_routes_are_mounted_and_pairwise_budget_is_bounded():
    response = client.post(
        "/v1/horizon/event-graph/build",
        json={"lookback_hours": 24, "max_events": 10, "max_candidates": 10, "max_signals": 10},
    )
    assert response.status_code == 200, response.text
    assert response.json()["engine_version"] == "horizon-event-graph-v0.1"

    invalid = client.post(
        "/v1/horizon/event-graph/build",
        json={"lookback_hours": 24, "max_events": 1200, "max_candidates": 1000, "max_signals": 10},
    )
    assert invalid.status_code == 422, invalid.text
