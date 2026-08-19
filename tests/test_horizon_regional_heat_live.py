from datetime import datetime, timedelta
from uuid import uuid4

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent
from app.services.horizon_heat_regions import HorizonRegionalHeatService


def _live_heat_event(db, *, key: str, department: str, first_observed_at: datetime) -> HorizonGlobalEvent:
    row = HorizonGlobalEvent(
        event_key=key,
        event_type="extreme_heat",
        title=f"Live Météo-France heat {department}",
        summary="Synthetic live official-primary heat event.",
        geography=["FR"],
        source="meteofrance-vigilance",
        source_url="https://vigilance.meteofrance.fr/fr",
        source_reliability=0.97,
        raw_facts={
            "normalized_facts": {
                "domain_id": department,
                "domain_kind": "department",
                "phenomenon_id": "6",
                "period": {
                    "begin_validity_time": "2026-08-10T10:00:00Z",
                    "end_validity_time": "2026-08-11T20:00:00Z",
                },
            }
        },
        occurred_at=first_observed_at,
        first_observed_at=first_observed_at,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_live_meteofrance_events_build_regional_state_and_duplicate_department_does_not_advance_clock():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    base = datetime(2026, 8, 10, 6, 0, 0)
    try:
        first_75 = _live_heat_event(
            db,
            key=f"live-75-a-{tag}",
            department="75",
            first_observed_at=base,
        )
        duplicate_75 = _live_heat_event(
            db,
            key=f"live-75-b-{tag}",
            department="75",
            first_observed_at=base + timedelta(hours=1),
        )
        one_department = HorizonRegionalHeatService(db).aggregate(
            start_at=datetime(2026, 8, 10),
            end_at=datetime(2026, 8, 12),
        )
        own_after_duplicate = [
            db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == event_id).one()
            for event_id in one_department["regional_event_ids"]
            if event_id
        ]
        assert not any(
            first_75.id in (event.raw_facts or {}).get("member_event_ids", [])
            or duplicate_75.id in (event.raw_facts or {}).get("member_event_ids", [])
            for event in own_after_duplicate
        )

        second_department_at = base + timedelta(hours=3)
        second_92 = _live_heat_event(
            db,
            key=f"live-92-{tag}",
            department="92",
            first_observed_at=second_department_at,
        )
        result = HorizonRegionalHeatService(db).aggregate(
            start_at=datetime(2026, 8, 10),
            end_at=datetime(2026, 8, 12),
        )
        regional_rows = [
            db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == event_id).one()
            for event_id in result["regional_event_ids"]
        ]
        own = next(
            event for event in regional_rows
            if second_92.id in (event.raw_facts or {}).get("member_event_ids", [])
        )
        assert own.source == "meteofrance-vigilance-derived"
        assert own.geography == ["FR", "REGION:11"]
        assert own.first_observed_at == second_department_at
        assert own.occurred_at == second_department_at
        assert set(own.raw_facts["departments"]) == {"75", "92"}
        assert set(own.raw_facts["member_sources"]) == {"meteofrance-vigilance"}
        assert own.raw_facts["first_observed_at_basis"] == "second_distinct_department_first_observed_at"
        assert result["critical_semantics"]["duplicate_snapshots_same_department_advance_regional_clock"] is False
    finally:
        db.close()
