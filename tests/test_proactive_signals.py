from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Intent, Signal, User
from app.services.engine import OpportunityEngine


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_time_sensitive_email_becomes_opportunity_when_it_matches_intent():
    db = _session()
    user = User(external_id="u1")
    db.add(user)
    db.flush()
    db.add(
        Intent(
            user_id=user.id,
            kind="career",
            statement="Trouver une formation innovation",
            target={"keywords": ["formation", "innovation"]},
            priority=0.9,
        )
    )
    db.add(
        Signal(
            user_id=user.id,
            source="google:gmail",
            type="email_message",
            payload={
                "message_id": "m1",
                "subject": "Dernier délai inscription formation innovation",
                "sender": "example@example.com",
                "snippet": "Les inscriptions expirent vendredi.",
            },
        )
    )
    db.commit()

    created = OpportunityEngine(db).run_for_user(user)
    assert len(created) == 1
    assert created[0].category == "timing"


def test_upcoming_calendar_event_matches_active_intent():
    db = _session()
    user = User(external_id="u2")
    db.add(user)
    db.flush()
    db.add(
        Intent(
            user_id=user.id,
            kind="career",
            statement="Préparer une certification digital",
            target={"keywords": ["certification", "digital"]},
            priority=0.8,
        )
    )
    db.add(
        Signal(
            user_id=user.id,
            source="google:calendar",
            type="calendar_event",
            payload={
                "event_id": "e1",
                "summary": "Session certification digital",
                "description": "Préparation",
                "start": (date.today() + timedelta(days=4)).isoformat(),
            },
        )
    )
    db.commit()

    created = OpportunityEngine(db).run_for_user(user)
    assert len(created) == 1
    assert created[0].proposed_action["type"] == "review_calendar_event"
