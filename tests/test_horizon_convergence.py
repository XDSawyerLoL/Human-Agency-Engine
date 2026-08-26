from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.horizon_source_schemas import HorizonSourceUpsert
from app.main import app
from app.services.horizon_convergence import HorizonConvergenceService
from app.services.horizon_sources import HorizonSourceService


client = TestClient(app)


def test_convergence_counts_unique_sources_not_repeated_rows_and_is_evidence_idempotent():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2026, 8, 20, 9, 0, 0)
    try:
        HorizonSourceService(db).sync_builtin_sources()
        behavioral_source = HorizonSourceService(db).upsert_source(
            HorizonSourceUpsert(
                source_key=f"test-rte-convergence-{tag}",
                name="Synthetic official statistical behavioral stream",
                source_class="official_statistical",
                adapter_kind="synthetic_test",
                domains=["test"],
                geography=["FR"],
                trust_weight=0.86,
                refresh_seconds=900,
                requires_credentials=False,
                enabled=True,
                metadata_json={"evidence_roles": ["behavioral_outcome", "physical_state"]},
            )
        )
        event = HorizonGlobalEvent(
            event_key=f"convergence-event-{tag}",
            event_type="extreme_heat_region",
            title="Synthetic convergence event",
            summary="fixture",
            geography=["FR", "REGION:11"],
            source="meteofrance-vigilance",
            source_url="https://vigilance.meteofrance.fr/fr",
            source_reliability=0.97,
            raw_facts={"region_code": "11"},
            occurred_at=base,
            first_observed_at=base,
            status="active",
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        for index, minute in enumerate((10, 20)):
            db.add(HorizonSocialSignal(
                event_id=event.id,
                signal_key=f"same-source-{tag}-{index}",
                signal_type="cooling_load_pressure_live",
                source=behavioral_source.source_key,
                geography=["FR", "REGION:11"],
                value=1100 + index,
                baseline=1000,
                normalized_score=1.5,
                direction="up",
                reliability=0.82,
                evidence={"fixture": True},
                observed_at=base + timedelta(minutes=minute),
            ))
        db.add(HorizonSocialSignal(
            event_id=event.id,
            signal_key=f"media-{tag}",
            signal_type="media_attention",
            source="gdelt-doc-2",
            geography=["FR"],
            value=10,
            baseline=2,
            normalized_score=2.0,
            direction="up",
            reliability=0.55,
            evidence={"fixture": True},
            observed_at=base + timedelta(minutes=30),
        ))
        db.commit()

        service = HorizonConvergenceService(db)
        first = service.build_snapshot(event.id, as_of=base + timedelta(hours=1))
        assert first["independent_sources"] == 3
        assert set(first["source_classes"]) >= {"official_primary", "official_statistical", "news_global"}
        assert "confirmation" in first["evidence_roles"]
        assert "behavioral_outcome" in first["evidence_roles"]
        assert "precursor" in first["evidence_roles"]
        assert "materialization" not in first["evidence_roles"]
        assert first["convergence_score_is_probability"] is False
        semantics = first["evidence_snapshot"]["critical_semantics"]
        assert semantics["repeated_rows_from_same_source_do_not_create_source_independence"] is True
        assert semantics["source_trust_counted_once_per_independence_family"] is True

        unchanged = service.build_snapshot(event.id, as_of=base + timedelta(hours=2))
        assert unchanged["id"] == first["id"]
        assert unchanged["replayed_existing_snapshot"] is True
        assert unchanged["as_of"] == first["as_of"]

        db.add(HorizonSocialSignal(
            event_id=event.id,
            signal_key=f"materialization-{tag}",
            signal_type="shortage_reports",
            source=f"independent-materialization-{tag}",
            geography=["FR"],
            value=1,
            baseline=0,
            normalized_score=1.2,
            direction="up",
            reliability=0.7,
            evidence={"fixture": True},
            observed_at=base + timedelta(hours=3),
        ))
        db.commit()
        changed = service.build_snapshot(event.id, as_of=base + timedelta(hours=4))
        assert changed["id"] != first["id"]
        assert changed["independent_sources"] == 4
        assert "materialization" in changed["evidence_roles"]
    finally:
        db.close()


def test_meteoalarm_relay_does_not_double_count_meteofrance_origin():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2026, 8, 20, 10, 0, 0)
    try:
        HorizonSourceService(db).sync_builtin_sources()
        meteoalarm = HorizonSourceService(db).upsert_source(
            HorizonSourceUpsert(
                source_key="meteoalarm:france",
                name="MeteoAlarm France test relay",
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
        event = HorizonGlobalEvent(
            event_key=f"family-event-{tag}",
            event_type="extreme_heat",
            title="Meteo-France warning",
            summary="fixture",
            geography=["FR", "75"],
            source="meteofrance-vigilance",
            source_url="https://vigilance.meteofrance.fr/fr",
            source_reliability=0.97,
            raw_facts={},
            occurred_at=base,
            first_observed_at=base,
            status="active",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        db.add(HorizonSocialSignal(
            event_id=event.id,
            signal_key=f"relay-{tag}",
            signal_type="heat_attention",
            source=meteoalarm.source_key,
            geography=["FR"],
            value=1,
            baseline=0,
            normalized_score=1.0,
            direction="up",
            reliability=0.93,
            evidence={"relay_fixture": True},
            observed_at=base + timedelta(minutes=10),
        ))
        db.commit()

        snapshot = HorizonConvergenceService(db).build_snapshot(event.id, as_of=base + timedelta(hours=1))
        assert snapshot["evidence_snapshot"]["provider_source_count"] == 2
        assert snapshot["independent_sources"] == 1
        assert snapshot["evidence_snapshot"]["family_members"]["weather-warning:france"] == [
            "meteoalarm:france",
            "meteofrance-vigilance",
        ]
    finally:
        db.close()


def test_convergence_capabilities_expose_gated_sources_without_faking_connection():
    response = client.get("/v1/horizon/convergence/capabilities")
    assert response.status_code == 200, response.text
    body = response.json()
    by_key = {item["source_key"]: item for item in body["capabilities"]}
    assert by_key["gdacs-official"]["status"] == "implemented_open_data"
    assert by_key["meteoalarm-atom"]["status"] == "implemented_open_data"
    assert by_key["meteoalarm-edr"]["status"] == "gated_external_access"
    assert by_key["rte-eco2mix-regional-tr"]["status"] == "implemented_open_data"
    assert by_key["vigicrues-official"]["status"] == "implemented_open_data"
    assert by_key["sncf-service-alerts"]["status"] == "implemented_open_data"
    assert by_key["google-trends-alpha"]["status"] == "gated_external_access"
    assert by_key["airparif-realtime"]["status"] == "gated_requires_provider_key"
    assert body["critical_semantics"]["gated_sources_are_not_claimed_as_connected"] is True
    assert body["critical_semantics"]["relay_or_aggregator_sources_can_share_independence_family"] is True


def test_live_convergence_route_can_run_with_network_sources_disabled():
    response = client.post(
        "/v1/horizon/live/convergence/poll",
        json={
            "include_gdelt": False,
            "include_gdacs": False,
            "include_meteofrance": False,
            "include_meteoalarm": False,
            "include_fuel": False,
            "include_rte_realtime": False,
            "include_vigicrues": False,
            "include_sncf": False,
            "include_world_pulse": False,
            "windy_points": [],
            "refresh_provisional_candidates": False,
            "snapshot_recent_active_events": False,
            "build_event_graph": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"] == []
    assert body["sources_succeeded"] == 0
    assert body["critical_semantics"]["source_count_is_not_truth_vote"] is True
    assert body["critical_semantics"]["convergence_score_is_probability"] is False
