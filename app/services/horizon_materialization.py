from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..horizon_materialization_models import HorizonMaterializationDetection
from ..horizon_materialization_schemas import HorizonMaterializationScanRequest
from ..horizon_models import (
    HorizonBehaviorPattern,
    HorizonForecast,
    HorizonForecastResolution,
    HorizonSocialSignal,
)
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class HorizonMaterializationService:
    ENGINE_VERSION = "horizon-materialization-detector-v0.1"
    DEFAULT_MIN_RELIABILITY = 0.65
    DEFAULT_STRONG_SOURCE_RELIABILITY = 0.85
    DEFAULT_MIN_NORMALIZED_SCORE = 0.50

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _materialization_signal_types(pattern: HorizonBehaviorPattern) -> set[str]:
        provenance = pattern.provenance or {}
        explicit = provenance.get("materialization_signal_types")
        if isinstance(explicit, list):
            values = {str(item) for item in explicit if str(item).strip()}
            if values:
                return values

        mapping = provenance.get("stage_signal_types")
        if isinstance(mapping, dict) and mapping:
            indexed: list[tuple[int, list]] = []
            for raw_index, values in mapping.items():
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                if isinstance(values, list) and values:
                    indexed.append((index, values))
            if indexed:
                _, values = max(indexed, key=lambda item: item[0])
                return {str(item) for item in values if str(item).strip()}
        return set()

    @staticmethod
    def _thresholds(pattern: HorizonBehaviorPattern) -> tuple[float, float, float]:
        provenance = pattern.provenance or {}
        min_reliability = float(
            provenance.get("materialization_min_reliability", HorizonMaterializationService.DEFAULT_MIN_RELIABILITY)
        )
        strong_reliability = float(
            provenance.get(
                "materialization_strong_source_reliability",
                HorizonMaterializationService.DEFAULT_STRONG_SOURCE_RELIABILITY,
            )
        )
        min_score = float(
            provenance.get(
                "materialization_min_normalized_score",
                HorizonMaterializationService.DEFAULT_MIN_NORMALIZED_SCORE,
            )
        )
        return min_reliability, strong_reliability, min_score

    def _first_materialization(
        self,
        forecast: HorizonForecast,
        pattern: HorizonBehaviorPattern,
        cutoff: datetime,
    ) -> dict | None:
        signal_types = self._materialization_signal_types(pattern)
        if not signal_types:
            return None
        min_reliability, strong_reliability, min_score = self._thresholds(pattern)
        rows = (
            self.db.query(HorizonSocialSignal)
            .filter(
                HorizonSocialSignal.event_id == forecast.event_id,
                HorizonSocialSignal.observed_at > forecast.as_of,
                HorizonSocialSignal.observed_at <= cutoff,
                HorizonSocialSignal.signal_type.in_(signal_types),
                HorizonSocialSignal.reliability >= min_reliability,
                HorizonSocialSignal.normalized_score >= min_score,
            )
            .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
            .all()
        )
        eligible = [row for row in rows if row.direction not in {"down", "flat"}]
        if not eligible:
            return None

        evidence: list[HorizonSocialSignal] = []
        sources: set[str] = set()
        for row in eligible:
            evidence.append(row)
            sources.add(row.source)
            strong_source = float(row.reliability) >= strong_reliability
            independently_corroborated = len(sources) >= 2
            if strong_source or independently_corroborated:
                return {
                    "became_obvious_at": row.observed_at,
                    "signals": list(evidence),
                    "sources": sorted(sources),
                    "signal_types": sorted(signal_types),
                    "rule": {
                        "engine": self.ENGINE_VERSION,
                        "basis": "first time final-stage materialization evidence satisfies strength rule",
                        "min_reliability": min_reliability,
                        "strong_source_reliability": strong_reliability,
                        "min_normalized_score": min_score,
                        "one_strong_source_or_two_distinct_sources": True,
                        "probability": False,
                        "causal_proof": False,
                    },
                }
        return None

    def scan(self, request: HorizonMaterializationScanRequest) -> dict:
        cutoff = _utc_naive(request.as_of) if request.as_of else datetime.utcnow()
        query = self.db.query(HorizonForecast).filter(HorizonForecast.status == "open")
        if request.mode != "all":
            query = query.filter(HorizonForecast.mode == request.mode)
        if request.forecast_ids:
            query = query.filter(HorizonForecast.id.in_(set(request.forecast_ids)))
        forecasts = (
            query.filter(HorizonForecast.as_of < cutoff)
            .order_by(HorizonForecast.as_of.asc(), HorizonForecast.id.asc())
            .limit(request.max_forecasts)
            .all()
        )

        resolved_ids: list[int] = []
        unresolved_ids: list[int] = []
        skipped_already_resolved: list[int] = []
        no_rule_ids: list[int] = []

        for forecast in forecasts:
            existing_resolution = (
                self.db.query(HorizonForecastResolution)
                .filter(HorizonForecastResolution.forecast_id == forecast.id)
                .one_or_none()
            )
            if existing_resolution is not None:
                skipped_already_resolved.append(forecast.id)
                continue

            pattern = (
                self.db.query(HorizonBehaviorPattern)
                .filter(HorizonBehaviorPattern.id == forecast.pattern_id)
                .one_or_none()
            )
            if pattern is None:
                unresolved_ids.append(forecast.id)
                continue
            if not self._materialization_signal_types(pattern):
                no_rule_ids.append(forecast.id)
                continue

            materialization = self._first_materialization(forecast, pattern, cutoff)
            if materialization is None:
                unresolved_ids.append(forecast.id)
                continue

            obvious_at = materialization["became_obvious_at"]
            lead_hours = round((obvious_at - forecast.as_of).total_seconds() / 3600.0, 3)
            if lead_hours <= 0:
                unresolved_ids.append(forecast.id)
                continue

            signal_ids = [row.id for row in materialization["signals"]]
            detection_key = sha256_dict(
                {
                    "engine": self.ENGINE_VERSION,
                    "forecast_id": forecast.id,
                    "became_obvious_at": obvious_at.isoformat(),
                    "signal_ids": signal_ids,
                }
            )
            detection = HorizonMaterializationDetection(
                detection_key=detection_key,
                forecast_id=forecast.id,
                event_id=forecast.event_id,
                pattern_id=forecast.pattern_id,
                became_obvious_at=obvious_at,
                predictive_lead_time_hours=lead_hours,
                evidence_signal_ids=signal_ids,
                evidence_sources=materialization["sources"],
                materialization_signal_types=materialization["signal_types"],
                rule_snapshot=materialization["rule"],
            )
            resolution = HorizonForecastResolution(
                forecast_id=forecast.id,
                outcome_occurred=True,
                outcome_summary=(
                    "Automatic materialization detected from final-stage evidence: "
                    + ", ".join(materialization["signal_types"])
                ),
                correctness="confirmed",
                became_obvious_at=obvious_at,
                personal_action_at=None,
                predictive_lead_time_hours=lead_hours,
                actionable_lead_time_hours=None,
                notes=(
                    "Automatically labeled by HORIZON materialization detector. "
                    "This confirms the forecasted observable outcome, not the causal mechanism."
                ),
            )
            self.db.add(detection)
            self.db.add(resolution)
            forecast.status = "resolved"
            forecast.calibration_status = "labeled"
            self.db.flush()
            resolved_ids.append(forecast.id)

        self.db.commit()
        return {
            "engine": self.ENGINE_VERSION,
            "mode": request.mode,
            "as_of": cutoff.isoformat(),
            "scanned": len(forecasts),
            "resolved": len(resolved_ids),
            "resolved_forecast_ids": resolved_ids,
            "still_unresolved_forecast_ids": unresolved_ids,
            "no_materialization_rule_forecast_ids": no_rule_ids,
            "already_resolved_forecast_ids": skipped_already_resolved,
            "predictive_lead_time_is_probability": False,
            "automatic_resolution_proves_causality": False,
        }

    def list_detections(self, limit: int = 100) -> list[HorizonMaterializationDetection]:
        return (
            self.db.query(HorizonMaterializationDetection)
            .order_by(HorizonMaterializationDetection.became_obvious_at.desc())
            .limit(limit)
            .all()
        )
