from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.base import NormalizedSignal
from app.db import Base
from app.models import ConnectorAccount, User
from app.services.ingestion import SignalIngestionService


def test_ingestion_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(external_id="u1")
    db.add(user)
    db.flush()
    connector = ConnectorAccount(
        user_id=user.id,
        provider="google",
        encrypted_token_json="encrypted",
        scopes=[],
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)

    signal = NormalizedSignal(
        external_key="gmail:abc",
        source="google:gmail",
        type="email_message",
        payload={"subject": "Deadline formation"},
        observed_at=datetime.utcnow(),
    )
    service = SignalIngestionService(db)
    assert service.ingest(connector, signal) is not None
    db.commit()
    assert service.ingest(connector, signal) is None
