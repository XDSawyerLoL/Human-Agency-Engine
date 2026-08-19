from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalCoverageInterval
from ..horizon_backtest_models import HorizonHistoricalBacktestRun
from ..horizon_backtest_schemas import HorizonHistoricalBacktestRequest
from ..horizon_expiry_schemas import HorizonForecastExpiryScanRequest
from ..horizon_models import (
    HorizonBehaviorPattern,
    HorizonForecast,
    HorizonForecastResolution,
    HorizonGlobalEvent,
    HorizonSocialSignal,
)
from ..horizon_schemas import HorizonForecastRequest
from ..models import Intent, StateFact, User
from .horizon import HorizonService
from .horizon_calibration import HorizonEmpiricalCalibrationService
from .horizon_coverage import HorizonHistoricalCoverageService
from .horizon_expiry import HorizonForecastExpiryService
from .horizon_materialization import HorizonMaterializationService
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class HorizonHistoricalBacktestFactory:
    ENGINE_VERSION = "horizon-historical-backtest-factory-v0.2"
    EXCLUDED_STATUS = "excluded_backtest_factory"
    EXCLUDED_CALIBRATION_STATUS = "excluded_factory_duplicate"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _event_type_matches(pattern: HorizonBehaviorPattern, event: HorizonGlobalEvent) -> bool:
        allowed = {str(item) for item in (pattern.event_types or [])}
        return not allowed or "*" in allowed or event.event_type in allowed

    @staticmethod
    def _earliest_eligible_cutoff(
        event: HorizonGlobalEvent,
        pattern: HorizonBehaviorPattern,
        signals: list[HorizonSocialSignal],
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> datetime | None:
        if not HorizonHistoricalBacktestFactory._event_type_matches(pattern, event):
            return None
        if pattern.knowledge_available_at > end_at:
            return None

        base = max(event.first_observed_at, pattern.knowledge_available_at, start_at)
        required = {str(item) for item in (pattern.required_signal_types or []) if str(item).strip()}
        if not required:
            return base if base <= end_at else None

        first_by_type: dict[str, datetime] = {}
        for signal in signals:
            if signal.observed_at > end_at:
                break
            if signal.signal_type in required and signal.signal_type not in first_by_type:
                first_by_type[signal.signal_type] = signal.observed_at
        if not required.issubset(first_by_type):
            return None
        cutoff = max([base, *[first_by_type[item] for item in sorted(required)]])
        return cutoff if cutoff <= end_at else None

    @staticmethod
    def _outcome_already_obvious(
        pattern: HorizonBehaviorPattern,
        signals: list[HorizonSocialSignal],
        cutoff: datetime,
    ) -> bool:
        signal_types = HorizonMaterializationService.materialization_signal_types_for_pattern(pattern)
        if not signal_types:
            return False
        min_reliability, _, min_score = HorizonMaterializationService._thresholds(pattern)
        return any(
            row.observed_at <= cutoff
            and row.signal_type in signal_types
            and row.direction not in {"down", "flat"}
            and float(row.reliability) >= min_reliability
            and float(row.normalized_score) >= min_score
            for row in signals
        )

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
        state_rows = (
            self.db.query(StateFact)
            .filter(StateFact.user_id == user.id, StateFact.observed_at <= end_at)
            .order_by(StateFact.id.asc())
            .all()
        )
        intent_rows = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.created_at <= end_at)
            .order_by(Intent.id.asc())
            .all()
        )
        coverage_rows = (
            self.db.query(HorizonHistoricalCoverageInterval)
            .filter(
                HorizonHistoricalCoverageInterval.start_at <= evaluation_as_of,
                HorizonHistoricalCoverageInterval.end_at >= end_at,
            )
            .order_by(HorizonHistoricalCoverageInterval.id.asc())
            .all()
        )
        return sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "user": {"id": user.id, "country": user.country},
                "events": [
                    {
                        "id": row.id,
                        "event_key": row.event_key,
                        "type": row.event_type,
                        "occurred_at": row.occurred_at.isoformat(),
                        "first_observed_at": row.first_observed_at.isoformat(),
                        "status": row.status,
                    }
                    for row in events
                ],
                "signals": [
                    {
                        "id": row.id,
                        "event_id": row.event_id,
                        "signal_key": row.signal_key,
                        "type": row.signal_type,
                        "observed_at": row.observed_at.isoformat(),
                    }
                    for row in signals
                    if row.observed_at <= evaluation_as_of
                ],
                "patterns": [
                    {
                        "id": row.id,
                        "pattern_key": row.pattern_key,
                        "knowledge_available_at": row.knowledge_available_at.isoformat(),
                        "required": row.required_signal_types,
                        "event_types": row.event_types,
                        "lag_low": row.expected_lag_hours_low,
                        "lag_high": row.expected_lag_hours_high,
                        "provenance": row.provenance,
                        "status": row.status,
                    }
                    for row in patterns
                ],
                "coverage": [
                    {
                        "id": row.id,
                        "key": row.coverage_key,
                        "kind": row.coverage_kind,
                        "event_types": row.event_types,
                        "signal_types": row.signal_types,
                        "geography": row.geography,
                        "start_at": row.start_at.isoformat(),
                        "end_at": row.end_at.isoformat(),
                        "completeness": row.completeness,
                    }
                    for row in coverage_rows
                ],
                "state_facts": [
                    {
                        "id": row.id,
                        "domain": row.domain,
                        "key": row.key,
                        "observed_at": row.observed_at.isoformat(),
                    }
                    for row in state_rows
                ],
                "intents": [
                    {
                        "id": row.id,
                        "kind": row.kind,
                        "created_at": row.created_at.isoformat(),
                        "active": row.active,
                    }
                    for row in intent_rows
                ],
            }
        )

    @staticmethod
    def _serialize_run(row: HorizonHistoricalBacktestRun, *, replayed: bool) -> dict:
        result = dict(row.result_snapshot or {})
        result.update(
            {
                "run_id": row.id,
                "run_key": row.run_key,
                "dataset_fingerprint": row.dataset_fingerprint,
                "created_at": row.created_at.isoformat(),
                "replayed_existing_run": replayed,
            }
        )
        return result

    def run(self, user: User, request: HorizonHistoricalBacktestRequest) -> dict:
        start_at = _utc_naive(request.start_at)
        end_at = _utc_naive(request.end_at)
        evaluation_as_of = _utc_naive(request.evaluation_as_of)
        if evaluation_as_of > datetime.utcnow() + timedelta(minutes=5):
            raise ValueError("historical backtest evaluation_as_of cannot be in the future")

        event_query = self.db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.first_observed_at >= start_at,
            HorizonGlobalEvent.first_observed_at <= end_at,
            HorizonGlobalEvent.status == "active",
        )
        if request.event_types:
            event_query = event_query.filter(HorizonGlobalEvent.event_type.in_(set(request.event_types)))
        events = (
            event_query.order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .limit(request.max_events)
            .all()
        )
        event_ids = [row.id for row in events]

        signals: list[HorizonSocialSignal] = []
        if event_ids:
            signals = (
                self.db.query(HorizonSocialSignal)
                .filter(
                    HorizonSocialSignal.event_id.in_(event_ids),
                    HorizonSocialSignal.observed_at <= evaluation_as_of,
                )
                .order_by(
                    HorizonSocialSignal.event_id.asc(),
                    HorizonSocialSignal.observed_at.asc(),
                    HorizonSocialSignal.id.asc(),
                )
                .all()
            )

        patterns = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= end_at,
            )
            .order_by(HorizonBehaviorPattern.id.asc())
            .all()
        )

        dataset_fingerprint = self._dataset_fingerprint(
            user,
            events,
            signals,
            patterns,
            end_at=end_at,
            evaluation_as_of=evaluation_as_of,
        )
        run_key = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "user_id": user.id,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "evaluation_as_of": evaluation_as_of.isoformat(),
                "event_types": sorted(set(request.event_types)),
                "max_events": request.max_events,
                "max_cases": request.max_cases,
                "dataset_fingerprint": dataset_fingerprint,
            }
        )
        existing = (
            self.db.query(HorizonHistoricalBacktestRun)
            .filter(HorizonHistoricalBacktestRun.run_key == run_key)
            .one_or_none()
        )
        if existing is not None:
            return self._serialize_run(existing, replayed=True)

        signals_by_event: dict[int, list[HorizonSocialSignal]] = defaultdict(list)
        for signal in signals:
            signals_by_event[signal.event_id].append(signal)

        skipped = {
            "event_pattern_mismatch_or_missing_precursor": 0,
            "no_materialization_rule": 0,
            "outcome_already_obvious_at_cutoff": 0,
            "outcome_window_after_evaluation": 0,
            "outcome_coverage_incomplete": 0,
            "cutoff_after_evaluation": 0,
            "forecast_not_created": 0,
        }
        planned: list[dict] = []
        coverage_service = HorizonHistoricalCoverageService(self.db)
        for event in events:
            event_signals = signals_by_event[event.id]
            for pattern in patterns:
                materialization_types = HorizonMaterializationService.materialization_signal_types_for_pattern(pattern)
                if not materialization_types:
                    if self._event_type_matches(pattern, event):
                        skipped["no_materialization_rule"] += 1
                    continue
                cutoff = self._earliest_eligible_cutoff(
                    event,
                    pattern,
                    event_signals,
                    start_at=start_at,
                    end_at=end_at,
                )
                if cutoff is None:
                    skipped["event_pattern_mismatch_or_missing_precursor"] += 1
                    continue
                if cutoff >= evaluation_as_of:
                    skipped["cutoff_after_evaluation"] += 1
                    continue
                if self._outcome_already_obvious(pattern, event_signals, cutoff):
                    skipped["outcome_already_obvious_at_cutoff"] += 1
                    continue
                coverage_end = cutoff + timedelta(
                    hours=float(pattern.expected_lag_hours_high)
                    + HorizonMaterializationService.grace_hours_for_pattern(pattern)
                )
                if coverage_end > evaluation_as_of:
                    skipped["outcome_window_after_evaluation"] += 1
                    continue
                coverage = coverage_service.signal_coverage(
                    event,
                    materialization_types,
                    start_at=cutoff,
                    end_at=coverage_end,
                )
                if not coverage["complete"]:
                    skipped["outcome_coverage_incomplete"] += 1
                    continue
                planned.append(
                    {
                        "event_id": event.id,
                        "event_key": event.event_key,
                        "event_type": event.event_type,
                        "pattern_id": pattern.id,
                        "pattern_key": pattern.pattern_key,
                        "cutoff": cutoff,
                        "outcome_window_end": coverage_end,
                        "outcome_coverage": coverage,
                    }
                )

        planned.sort(key=lambda item: (item["cutoff"], item["event_id"], item["pattern_id"]))
        total_planned_before_limit = len(planned)
        truncated = total_planned_before_limit > request.max_cases
        planned = planned[: request.max_cases]

        groups: dict[tuple[int, datetime], set[int]] = defaultdict(set)
        planned_by_pair: dict[tuple[int, int], dict] = {}
        for item in planned:
            groups[(item["event_id"], item["cutoff"])].add(item["pattern_id"])
            planned_by_pair[(item["event_id"], item["pattern_id"])] = item

        selected_forecast_ids: list[int] = []
        excluded_collateral_ids: list[int] = []
        selected_cases: list[dict] = []
        horizon = HorizonService(self.db)

        for (event_id, cutoff), intended_pattern_ids in sorted(
            groups.items(), key=lambda item: (item[0][1], item[0][0])
        ):
            preexisting_ids = {
                row.id
                for row in self.db.query(HorizonForecast)
                .filter(
                    HorizonForecast.user_id == user.id,
                    HorizonForecast.event_id == event_id,
                    HorizonForecast.mode == "backtest",
                    HorizonForecast.as_of == cutoff,
                )
                .all()
            }
            rows = horizon.forecast_user(
                user,
                HorizonForecastRequest(event_id=event_id, as_of=cutoff, mode="backtest"),
            )
            target_by_pattern = {row.pattern_id: row for row in rows if row.pattern_id in intended_pattern_ids}
            for pattern_id in sorted(intended_pattern_ids):
                row = target_by_pattern.get(pattern_id)
                if row is None:
                    skipped["forecast_not_created"] += 1
                    continue
                existing_resolution = (
                    self.db.query(HorizonForecastResolution)
                    .filter(HorizonForecastResolution.forecast_id == row.id)
                    .one_or_none()
                )
                if row.status == self.EXCLUDED_STATUS and existing_resolution is None:
                    row.status = "open"
                    row.calibration_status = "uncalibrated"
                if row.id not in selected_forecast_ids:
                    selected_forecast_ids.append(row.id)
                    plan = planned_by_pair[(event_id, pattern_id)]
                    selected_cases.append(
                        {
                            "event_id": event_id,
                            "pattern_id": pattern_id,
                            "forecast_id": row.id,
                            "cutoff": cutoff.isoformat(),
                            "outcome_window_end": plan["outcome_window_end"].isoformat(),
                            "outcome_coverage": plan["outcome_coverage"],
                        }
                    )

            for row in rows:
                if row.pattern_id in intended_pattern_ids or row.id in preexisting_ids:
                    continue
                existing_resolution = (
                    self.db.query(HorizonForecastResolution)
                    .filter(HorizonForecastResolution.forecast_id == row.id)
                    .one_or_none()
                )
                if existing_resolution is None:
                    row.status = self.EXCLUDED_STATUS
                    row.calibration_status = self.EXCLUDED_CALIBRATION_STATUS
                    excluded_collateral_ids.append(row.id)
            self.db.commit()

        for offset in range(0, len(selected_forecast_ids), 500):
            chunk = selected_forecast_ids[offset : offset + 500]
            if not chunk:
                continue
            HorizonForecastExpiryService(self.db).scan(
                HorizonForecastExpiryScanRequest(
                    mode="backtest",
                    as_of=evaluation_as_of,
                    max_forecasts=len(chunk),
                    forecast_ids=chunk,
                )
            )

        resolutions = {}
        if selected_forecast_ids:
            resolutions = {
                row.forecast_id: row
                for row in self.db.query(HorizonForecastResolution)
                .filter(HorizonForecastResolution.forecast_id.in_(selected_forecast_ids))
                .all()
            }

        counts = {"confirmed": 0, "partial": 0, "false": 0, "inconclusive": 0, "unresolved": 0}
        lead_times: list[float] = []
        for case in selected_cases:
            resolution = resolutions.get(case["forecast_id"])
            if resolution is None:
                case["correctness"] = "unresolved"
                counts["unresolved"] += 1
                continue
            correctness = resolution.correctness
            case["correctness"] = correctness
            case["became_obvious_at"] = (
                resolution.became_obvious_at.isoformat() if resolution.became_obvious_at else None
            )
            case["predictive_lead_time_hours"] = resolution.predictive_lead_time_hours
            counts[correctness if correctness in counts else "inconclusive"] += 1
            if resolution.predictive_lead_time_hours is not None and correctness in {"confirmed", "partial"}:
                lead_times.append(float(resolution.predictive_lead_time_hours))

        calibration = HorizonEmpiricalCalibrationService(self.db).profile(
            user,
            mode="backtest",
            as_of=evaluation_as_of,
        )
        result = {
            "engine": self.ENGINE_VERSION,
            "window": {
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "evaluation_as_of": evaluation_as_of.isoformat(),
            },
            "events_selected": len(events),
            "event_ids": event_ids,
            "patterns_considered": len(patterns),
            "planned_cases_before_limit": total_planned_before_limit,
            "selected_cases": len(selected_cases),
            "truncated_by_max_cases": truncated,
            "outcomes": counts,
            "mean_predictive_lead_time_hours": (
                round(sum(lead_times) / len(lead_times), 3) if lead_times else None
            ),
            "excluded_collateral_forecasts": len(excluded_collateral_ids),
            "skipped": skipped,
            "calibration_after_run": calibration,
            "critical_semantics": {
                "one_case_per_event_pattern_at_earliest_eligible_cutoff": True,
                "future_signals_visible_to_forecast": False,
                "outcome_already_obvious_cases_disqualified": True,
                "only_patterns_with_materialization_rules_are_scored": True,
                "complete_outcome_signal_coverage_required_for_every_scored_case": True,
                "absence_of_signal_without_complete_coverage_counts_as_failure": False,
                "positive_cases_bypass_coverage_gate": False,
                "numeric_probabilities_enabled": False,
                "historical_source_scope": "already_ingested_horizon_event_signal_and_coverage_snapshots",
                "historical_event_status_scope": "active_snapshots_only_v0.2",
            },
        }
        run = HorizonHistoricalBacktestRun(
            run_key=run_key,
            user_id=user.id,
            engine_version=self.ENGINE_VERSION,
            requested_start_at=start_at,
            requested_end_at=end_at,
            evaluation_as_of=evaluation_as_of,
            event_types=sorted(set(request.event_types)),
            max_events=request.max_events,
            max_cases=request.max_cases,
            dataset_fingerprint=dataset_fingerprint,
            selected_event_ids=event_ids,
            selected_forecast_ids=selected_forecast_ids,
            excluded_collateral_forecast_ids=excluded_collateral_ids,
            case_snapshot=selected_cases,
            result_snapshot=result,
            status="completed",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return self._serialize_run(run, replayed=False)

    def list_runs(self, user: User, limit: int = 50) -> list[dict]:
        rows = (
            self.db.query(HorizonHistoricalBacktestRun)
            .filter(HorizonHistoricalBacktestRun.user_id == user.id)
            .order_by(HorizonHistoricalBacktestRun.created_at.desc(), HorizonHistoricalBacktestRun.id.desc())
            .limit(limit)
            .all()
        )
        return [self._serialize_run(row, replayed=False) for row in rows]
