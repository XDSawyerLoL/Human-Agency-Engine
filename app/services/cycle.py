from __future__ import annotations

from sqlalchemy.orm import Session

from ..connectors.google import GoogleReadOnlyConnector
from ..models import ConnectorAccount, User
from .acquisition import InformationAcquisitionService
from .engine import OpportunityEngine
from .synthesis import SynthesisService


class AgencyCycle:
    def __init__(self, db: Session):
        self.db = db

    def run(self) -> dict:
        connector_results: list[dict] = []
        created_opportunities = 0
        synthesis_totals = {
            "generated": 0,
            "evaluated": 0,
            "ready_for_review": 0,
            "needs_information": 0,
            "rejected": 0,
            "queued_notifications": 0,
            "suppressed_notifications": 0,
        }
        acquisition_totals = {
            "candidates_scanned": 0,
            "needs_created": 0,
            "auto_resolved": 0,
            "open_needs": 0,
        }

        accounts = (
            self.db.query(ConnectorAccount)
            .filter(ConnectorAccount.enabled == True)  # noqa: E712
            .all()
        )
        for account in accounts:
            if account.provider == "google":
                try:
                    connector_results.append(GoogleReadOnlyConnector(self.db).sync(account.id))
                except Exception as exc:
                    connector_results.append(
                        {
                            "provider": account.provider,
                            "account_id": account.id,
                            "error": str(exc),
                        }
                    )

        engine = OpportunityEngine(self.db)
        synthesis = SynthesisService(self.db)
        acquisition = InformationAcquisitionService(self.db)
        for user in self.db.query(User).all():
            created = engine.run_for_user(user)
            created_opportunities += len(created)
            synthesis_result = synthesis.run(user)
            for key in synthesis_totals:
                synthesis_totals[key] += int(synthesis_result.get(key, 0))
            acquisition_result = acquisition.materialize(user)
            for key in acquisition_totals:
                acquisition_totals[key] += int(acquisition_result.get(key, 0))

        return {
            "connectors": connector_results,
            "created_opportunities": created_opportunities,
            "synthesis": synthesis_totals,
            "information_acquisition": acquisition_totals,
        }
