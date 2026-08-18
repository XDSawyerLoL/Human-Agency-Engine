from __future__ import annotations

from sqlalchemy.orm import Session

from ..connectors.base import NormalizedSignal
from ..models import ConnectorAccount, IngestionRecord, Signal


class SignalIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest(
        self,
        connector: ConnectorAccount,
        normalized: NormalizedSignal,
    ) -> Signal | None:
        existing = (
            self.db.query(IngestionRecord)
            .filter(
                IngestionRecord.connector_id == connector.id,
                IngestionRecord.external_key == normalized.external_key,
            )
            .one_or_none()
        )
        if existing:
            return None

        signal = Signal(
            user_id=connector.user_id,
            source=normalized.source,
            type=normalized.type,
            payload=normalized.payload,
            observed_at=normalized.observed_at,
        )
        self.db.add(signal)
        self.db.flush()

        self.db.add(
            IngestionRecord(
                connector_id=connector.id,
                external_key=normalized.external_key,
                signal_id=signal.id,
            )
        )
        return signal
