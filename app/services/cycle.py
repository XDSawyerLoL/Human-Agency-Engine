from __future__ import annotations

from sqlalchemy.orm import Session

from ..connectors.google import GoogleReadOnlyConnector
from ..models import ConnectorAccount, User
from .engine import OpportunityEngine


class AgencyCycle:
    def __init__(self, db: Session):
        self.db = db

    def run(self) -> dict:
        connector_results: list[dict] = []
        created_opportunities = 0

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
        for user in self.db.query(User).all():
            created_opportunities += len(engine.run_for_user(user))

        return {
            "connectors": connector_results,
            "created_opportunities": created_opportunities,
        }
