from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.horizon_reevaluation_models import HorizonReevaluationDecision
from app.horizon_reevaluation_schemas import HorizonReevaluationRequest
from app.main import app
from app.models import Notification, Opportunity, StateFact, User
from app.services.horizon_reevaluation import HorizonReevaluationService
from app.services.horizon_response_library import HorizonResponseLibraryService

api = TestClient(app)


def _user(db, suffix: str, department: str | None) -> User:
    user = User(
        external_id=f"horizon-reeval-{suffix}-{uuid4().hex[:8]}",
        country="FR",
        currency="EUR",
        timezone="Europe/Paris",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if department is not None:
        db.add(
            StateFact(
                user_id=user.id,
                domain="location",
                key="department",
                value={"code": department},
                source="test",
                confidence=1.0,
                sensitivity="personal",
                observed_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        db.commit()
    return user


def _heat_event(db) -> HorizonGlobalEvent:
    now = datetime.utcnow()
    event = HorizonGlobalEvent(
        event_key=f"reeval-heat-{uuid4().hex}",
        event_type="extreme_heat",
        title="Official heat warning in department 92",
        summary="Official primary-source heat warning fixture.",
        geography=["FR", "92"],
        source="meteofrance-vigilance",
        source_url="https://example.invalid/official",
        source_reliability=1.0,
        raw_facts={
            "personal_scope": {
                "all": [
                    {
                        "state_key": "location.department",
                        "value_path": "code",
                        "operator": "equals",
                        "value": "92",
                    }
                ]
            },
            "normalized_inference": {"phenomenon": "heatwave"},
        },
        occurred_at=now - timedelta(hours=1),
        first_observed_at=now - timedelta(minutes=2),
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _signal(db, event_id: int, signal_type: str) -> HorizonSocialSignal:
    row = HorizonSocialSignal(
        event_id=event_id,
        signal_key=f"reeval-{signal_type}-{uuid4().hex}",
        signal_type=signal_type,
        source="test-behavioral-sensor",
        geography=["FR", "92"],
        value=4.0,
        baseline=1.0,
        normalized_score=3.0,
        direction="up",
        reliability=1.0,
        evidence={
            "diagnostic_only": True,
            "does_not_measure": ["event_probability"],
        },
        observed_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_reevaluation_only_surfaces_material_changes_and_scope_mismatch_never_notifies():
    db = SessionLocal()
    try:
        local = _user(db, "local", "92")
        remote = _user(db, "remote", "29")
        event = _heat_event(db)
        library = HorizonResponseLibraryService(db).sync_builtins()
        pattern = next(item for item in library if item.pattern_key == "builtin-extreme-heat-cooling-demand-v1")
        _signal(db, event.id, "media_attention")

        service = HorizonReevaluationService(db)
        first = service.run(HorizonReevaluationRequest(max_events=1, max_users=50000))
        assert first["errors_count"] == 0
        assert first["external_action_executed"] is False
        assert first["attention_score_is_probability"] is False

        local_decisions = (
            db.query(HorizonReevaluationDecision)
            .filter(
                HorizonReevaluationDecision.user_id == local.id,
                HorizonReevaluationDecision.event_id == event.id,
                HorizonReevaluationDecision.pattern_id == pattern.id,
            )
            .order_by(HorizonReevaluationDecision.id.asc())
            .all()
        )
        assert len(local_decisions) == 1
        assert local_decisions[0].surface_requested is True
        assert local_decisions[0].status == "queued"
        assert local_decisions[0].attention_band in {"attention", "urgent_attention"}
        assert local_decisions[0].notification_id is not None

        remote_decisions = (
            db.query(HorizonReevaluationDecision)
            .filter(
                HorizonReevaluationDecision.user_id == remote.id,
                HorizonReevaluationDecision.event_id == event.id,
                HorizonReevaluationDecision.pattern_id == pattern.id,
            )
            .all()
        )
        assert len(remote_decisions) == 1
        assert remote_decisions[0].status == "scope_mismatch"
        assert remote_decisions[0].surface_requested is False
        assert remote_decisions[0].assessment_id is None
        assert remote_decisions[0].notification_id is None

        notification_count = (
            db.query(Notification)
            .filter(Notification.user_id == local.id)
            .count()
        )
        opportunity_count = (
            db.query(Opportunity)
            .filter(Opportunity.user_id == local.id, Opportunity.category == "horizon_extreme_heat")
            .count()
        )
        assert notification_count == 1
        assert opportunity_count == 1

        unchanged = service.run(HorizonReevaluationRequest(max_events=1, max_users=50000))
        assert unchanged["errors_count"] == 0
        assert (
            db.query(HorizonReevaluationDecision)
            .filter(
                HorizonReevaluationDecision.user_id == local.id,
                HorizonReevaluationDecision.event_id == event.id,
                HorizonReevaluationDecision.pattern_id == pattern.id,
            )
            .count()
            == 1
        )
        assert db.query(Notification).filter(Notification.user_id == local.id).count() == 1

        # A genuine next-stage signal changes the input fingerprint and advances
        # the sequential behavioral cascade. Re-evaluation is therefore valid,
        # but the existing category cooldown may still protect the user's attention.
        _signal(db, event.id, "cooling_search_interest")
        advanced = service.run(HorizonReevaluationRequest(max_events=1, max_users=50000))
        assert advanced["errors_count"] == 0

        local_decisions = (
            db.query(HorizonReevaluationDecision)
            .filter(
                HorizonReevaluationDecision.user_id == local.id,
                HorizonReevaluationDecision.event_id == event.id,
                HorizonReevaluationDecision.pattern_id == pattern.id,
            )
            .order_by(HorizonReevaluationDecision.id.asc())
            .all()
        )
        assert len(local_decisions) == 2
        assert local_decisions[1].surface_requested is True
        assert local_decisions[1].cascade_stage != local_decisions[0].cascade_stage
        assert local_decisions[1].status == "suppressed"
        assert "cooldown" in local_decisions[1].reason
        assert db.query(Notification).filter(Notification.user_id == local.id).count() == 2
    finally:
        db.close()


def test_horizon_reevaluation_route_is_mounted(monkeypatch):
    def fake_run(self, request):
        return {
            "events_scanned": 1,
            "users_available": 2,
            "event_pattern_pairs": 1,
            "user_pairs_scanned": 2,
            "scope_mismatches": 1,
            "unchanged_inputs": 0,
            "assessments": 1,
            "silent_decisions": 0,
            "surface_requested": 1,
            "queued_notifications": 1,
            "suppressed_notifications": 0,
            "resumed_decisions": 0,
            "errors": [],
            "errors_count": 0,
            "external_action_executed": False,
            "attention_score_is_probability": False,
        }

    monkeypatch.setattr(HorizonReevaluationService, "run", fake_run)
    response = api.post(
        "/v1/horizon/reevaluate/run",
        json={"max_events": 10, "max_users": 100, "material_score_delta": 0.12},
    )
    assert response.status_code == 200, response.text
    assert response.json()["queued_notifications"] == 1
    assert response.json()["external_action_executed"] is False
