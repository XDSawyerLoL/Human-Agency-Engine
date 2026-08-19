from __future__ import annotations

from datetime import datetime

from ..horizon_backfill_models import HorizonHistoricalCoverageInterval
from ..horizon_models import HorizonBehaviorPattern, HorizonGlobalEvent, HorizonSocialSignal
from ..models import User
from .horizon_backtest import HorizonHistoricalBacktestFactory
from .policy import sha256_dict


class HorizonCoverageAwareHistoricalBacktestFactory(HorizonHistoricalBacktestFactory):
    """Backtest factory with cache invalidation for newly imported coverage evidence.

    The v0.2 base factory already fingerprints coverage that spans the broad request
    window. This compatibility layer deliberately fingerprints the whole historical
    coverage catalog visible by evaluation time as well. That means importing a
    narrower but decisive outcome-coverage interval can never accidentally replay an
    older run created before that evidence existed.
    """

    def _dataset_fingerprint(
        self,
        user: User,
        events: list[HorizonGlobalEvent],
        signals: list[HorizonSocialSignal],
        patterns: list[HorizonBehaviorPattern],
        *,
        end_at: datetime,
        evaluation_as_of: datetime,
    ) -> str:
        base = super()._dataset_fingerprint(
            user,
            events,
            signals,
            patterns,
            end_at=end_at,
            evaluation_as_of=evaluation_as_of,
        )
        rows = (
            self.db.query(HorizonHistoricalCoverageInterval)
            .filter(HorizonHistoricalCoverageInterval.start_at <= evaluation_as_of)
            .order_by(HorizonHistoricalCoverageInterval.id.asc())
            .all()
        )
        return sha256_dict(
            {
                "base_dataset_fingerprint": base,
                "coverage_catalog": [
                    {
                        "coverage_key": row.coverage_key,
                        "source_id": row.source_id,
                        "coverage_kind": row.coverage_kind,
                        "event_types": row.event_types,
                        "signal_types": row.signal_types,
                        "geography": row.geography,
                        "start_at": row.start_at.isoformat(),
                        "end_at": row.end_at.isoformat(),
                        "completeness": row.completeness,
                        "basis": row.basis,
                    }
                    for row in rows
                ],
            }
        )
