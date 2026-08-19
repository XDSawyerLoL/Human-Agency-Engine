from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt

from sqlalchemy.orm import Session

from ..horizon_expiry_models import HorizonForecastExpiry
from ..horizon_models import (
    HorizonBehaviorPattern,
    HorizonForecast,
    HorizonForecastResolution,
    HorizonGlobalEvent,
)
from ..models import User


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    p = successes / total
    denominator = 1.0 + (z * z / total)
    centre = p + (z * z / (2.0 * total))
    margin = z * sqrt((p * (1.0 - p) / total) + (z * z / (4.0 * total * total)))
    low = max(0.0, (centre - margin) / denominator)
    high = min(1.0, (centre + margin) / denominator)
    return round(low, 4), round(high, 4)


class HorizonEmpiricalCalibrationService:
    """Measure whether HORIZON has earned the right to emit numeric probabilities.

    The existing predictive_score remains a diagnostic score. This service only
    evaluates resolved historical forecasts. Numeric probability use stays gated
    until there is enough binary, event-diverse evidence.
    """

    ENGINE_VERSION = "horizon-empirical-calibration-v0.2"
    MIN_GLOBAL_BINARY_LABELS = 50
    MIN_GLOBAL_DISTINCT_EVENTS = 10
    MIN_STRATUM_BINARY_LABELS = 20
    MIN_STRATUM_DISTINCT_EVENTS = 5

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _label_available_at(
        resolution: HorizonForecastResolution,
        expiry_deadline: datetime | None = None,
    ) -> datetime:
        # Positive materialization becomes knowable when the outcome became obvious.
        if resolution.became_obvious_at is not None:
            return resolution.became_obvious_at
        # An automatic historical miss becomes knowable when its declared validity
        # window expires, not when a later backtest process happens to record it.
        if resolution.correctness == "false" and expiry_deadline is not None:
            return expiry_deadline
        # Manual/inconclusive labels remain conservatively tied to entry time so a
        # backtest cannot learn from a human label that did not exist at the cutoff.
        return resolution.resolved_at

    @staticmethod
    def _binary_outcome(correctness: str) -> int | None:
        if correctness == "confirmed":
            return 1
        if correctness == "false":
            return 0
        return None

    @staticmethod
    def _weighted_outcome(correctness: str) -> float | None:
        if correctness == "confirmed":
            return 1.0
        if correctness == "partial":
            return 0.5
        if correctness == "false":
            return 0.0
        return None

    @classmethod
    def _binary_stats(cls, items: list[dict]) -> dict:
        binary = [item for item in items if item["binary_outcome"] is not None]
        total = len(binary)
        successes = sum(int(item["binary_outcome"]) for item in binary)
        failures = total - successes
        distinct_events = len({item["event_id"] for item in binary})
        low, high = _wilson_interval(successes, total)
        observed_rate = round(successes / total, 4) if total else None
        return {
            "binary_labels": total,
            "successes": successes,
            "failures": failures,
            "distinct_events": distinct_events,
            "observed_success_rate": observed_rate,
            "wilson_95_low": low,
            "wilson_95_high": high,
        }

    def profile(
        self,
        user: User,
        *,
        mode: str = "backtest",
        as_of: datetime | None = None,
    ) -> dict:
        cutoff = _utc_naive(as_of) if as_of else None
        query = (
            self.db.query(
                HorizonForecast,
                HorizonForecastResolution,
                HorizonGlobalEvent,
                HorizonBehaviorPattern,
            )
            .join(HorizonForecastResolution, HorizonForecastResolution.forecast_id == HorizonForecast.id)
            .join(HorizonGlobalEvent, HorizonGlobalEvent.id == HorizonForecast.event_id)
            .join(HorizonBehaviorPattern, HorizonBehaviorPattern.id == HorizonForecast.pattern_id)
            .filter(HorizonForecast.user_id == user.id)
        )
        if mode != "all":
            query = query.filter(HorizonForecast.mode == mode)

        joined_rows = query.all()
        forecast_ids = [forecast.id for forecast, _, _, _ in joined_rows]
        expiry_by_forecast: dict[int, HorizonForecastExpiry] = {}
        if forecast_ids:
            expiry_by_forecast = {
                row.forecast_id: row
                for row in self.db.query(HorizonForecastExpiry)
                .filter(HorizonForecastExpiry.forecast_id.in_(forecast_ids))
                .all()
            }

        items: list[dict] = []
        for forecast, resolution, event, pattern in joined_rows:
            expiry = expiry_by_forecast.get(forecast.id)
            label_available_at = self._label_available_at(
                resolution,
                expiry.expiry_deadline if expiry is not None else None,
            )
            if cutoff is not None:
                if forecast.as_of > cutoff:
                    continue
                if _utc_naive(label_available_at) > cutoff:
                    continue
            weighted = self._weighted_outcome(resolution.correctness)
            if weighted is None:
                continue
            binary = self._binary_outcome(resolution.correctness)
            items.append(
                {
                    "forecast_id": forecast.id,
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "pattern_id": pattern.id,
                    "pattern_key": pattern.pattern_key,
                    "likelihood_band": forecast.likelihood_band,
                    "predictive_score": float(forecast.predictive_score),
                    "correctness": resolution.correctness,
                    "weighted_outcome": weighted,
                    "binary_outcome": binary,
                    "label_available_at": label_available_at,
                    "predictive_lead_time_hours": resolution.predictive_lead_time_hours,
                }
            )

        decisive_labels = len(items)
        weighted_precision = (
            round(sum(item["weighted_outcome"] for item in items) / decisive_labels, 4)
            if decisive_labels
            else None
        )
        lead_times = [
            float(item["predictive_lead_time_hours"])
            for item in items
            if item["predictive_lead_time_hours"] is not None
            and item["correctness"] in {"confirmed", "partial"}
        ]
        alignment = [
            abs(float(item["predictive_score"]) - float(item["binary_outcome"]))
            for item in items
            if item["binary_outcome"] is not None
        ]

        global_stats = self._binary_stats(items)
        global_ready = (
            mode == "backtest"
            and global_stats["binary_labels"] >= self.MIN_GLOBAL_BINARY_LABELS
            and global_stats["distinct_events"] >= self.MIN_GLOBAL_DISTINCT_EVENTS
            and global_stats["successes"] > 0
            and global_stats["failures"] > 0
        )

        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for item in items:
            grouped[(item["pattern_key"], item["likelihood_band"])].append(item)

        strata = []
        for (pattern_key, band), group in sorted(grouped.items()):
            stats = self._binary_stats(group)
            eligible = (
                global_ready
                and stats["binary_labels"] >= self.MIN_STRATUM_BINARY_LABELS
                and stats["distinct_events"] >= self.MIN_STRATUM_DISTINCT_EVENTS
                and stats["successes"] > 0
                and stats["failures"] > 0
            )
            strata.append(
                {
                    "pattern_key": pattern_key,
                    "likelihood_band": band,
                    **stats,
                    "probability_interval_eligible": eligible,
                }
            )

        return {
            "engine": self.ENGINE_VERSION,
            "mode": mode,
            "as_of": cutoff.isoformat() if cutoff else None,
            "decisive_labels": decisive_labels,
            "weighted_precision": weighted_precision,
            "mean_predictive_lead_time_hours": (
                round(sum(lead_times) / len(lead_times), 3) if lead_times else None
            ),
            "score_alignment_mae": round(sum(alignment) / len(alignment), 4) if alignment else None,
            "score_alignment_is_probability_calibration": False,
            "global_binary_evidence": global_stats,
            "probability_calibration_enabled": False,
            "probability_calibration_ready": global_ready,
            "eligibility_thresholds": {
                "global_binary_labels": self.MIN_GLOBAL_BINARY_LABELS,
                "global_distinct_events": self.MIN_GLOBAL_DISTINCT_EVENTS,
                "stratum_binary_labels": self.MIN_STRATUM_BINARY_LABELS,
                "stratum_distinct_events": self.MIN_STRATUM_DISTINCT_EVENTS,
                "requires_successes_and_failures": True,
                "training_mode": "backtest_only",
            },
            "strata": strata,
            "critical_semantics": {
                "predictive_score_is_probability": False,
                "partial_labels_used_for_probability_rate": False,
                "wilson_interval_is_descriptive_until_gate_passes": True,
                "historical_cutoff_excludes_labels_not_yet_available": True,
                "automatic_expiry_label_available_at_deadline": True,
            },
        }
