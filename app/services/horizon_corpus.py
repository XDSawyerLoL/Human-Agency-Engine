from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy.orm import Session

from ..horizon_backfill_schemas import (
    HorizonMeteoFranceArchiveBackfillRequest,
    HorizonRteCoolingLoadBackfillRequest,
)
from ..horizon_backtest_models import HorizonHistoricalBacktestRun
from ..horizon_backtest_schemas import HorizonHistoricalBacktestRequest
from ..horizon_corpus_models import HorizonCalibrationCorpusRun, HorizonCalibrationCorpusSlice
from ..horizon_corpus_schemas import HorizonCalibrationCorpusBuildRequest
from ..horizon_models import HorizonForecastResolution
from ..models import User
from .horizon_backfill import HorizonHistoricalBackfillService, METEOFRANCE_ARCHIVE_AVAILABLE_FROM
from .horizon_backtest_coverage import HorizonCoverageAwareHistoricalBacktestFactory
from .horizon_calibration import HorizonEmpiricalCalibrationService
from .horizon_rte import HorizonRteCoolingLoadBackfillService
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class HorizonCalibrationCorpusService:
    ENGINE_VERSION = "horizon-calibration-corpus-builder-v0.1"
    CORPUS_SPEC_VERSION = "heat-mf-rte-v1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _slice_plan(start_at: datetime, end_at: datetime, slice_days: int, grace_days: int) -> list[dict]:
        plan: list[dict] = []
        cursor = start_at
        index = 0
        while cursor <= end_at:
            nominal_end = cursor + timedelta(days=slice_days) - timedelta(microseconds=1)
            slice_end = min(end_at, nominal_end)
            plan.append(
                {
                    "slice_index": index,
                    "start_at": cursor,
                    "end_at": slice_end,
                    "evaluation_as_of": slice_end + timedelta(days=grace_days),
                }
            )
            cursor = slice_end + timedelta(microseconds=1)
            index += 1
        return plan

    @classmethod
    def _precommitted_spec(cls, request: HorizonCalibrationCorpusBuildRequest) -> dict:
        return {
            "corpus_spec_version": cls.CORPUS_SPEC_VERSION,
            "event_family": "extreme_heat_region",
            "trigger_archive": "meteofrance-vigilance-archive",
            "outcome_stream": "rte-eco2mix-regional-cons-def",
            "materialization_signal": "cooling_load_pressure",
            "meteo_min_color_id": request.meteo_min_color_id,
            "meteo_merge_gap_hours": request.meteo_merge_gap_hours,
            "rte_baseline_lookback_days": request.rte_baseline_lookback_days,
            "rte_minimum_lift_ratio": request.rte_minimum_lift_ratio,
            "rte_minimum_afternoon_points": request.rte_minimum_afternoon_points,
            "outcome_grace_days": request.outcome_grace_days,
            "thresholds_precommitted_before_outcome_scoring": True,
            "thresholds_tuned_from_this_corpus": False,
        }

    def _get_or_create_run(self, user: User, request: HorizonCalibrationCorpusBuildRequest) -> HorizonCalibrationCorpusRun:
        start_at = _utc_naive(request.start_at)
        end_at = _utc_naive(request.end_at)
        spec = self._precommitted_spec(request)
        corpus_key = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "user_id": user.id,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "request": request.model_dump(mode="json", exclude={"max_slices_per_call"}),
                "precommitted_spec": spec,
            }
        )
        existing = self.db.query(HorizonCalibrationCorpusRun).filter(
            HorizonCalibrationCorpusRun.corpus_key == corpus_key
        ).one_or_none()
        if existing is not None:
            return existing

        run = HorizonCalibrationCorpusRun(
            corpus_key=corpus_key,
            user_id=user.id,
            engine_version=self.ENGINE_VERSION,
            requested_start_at=start_at,
            requested_end_at=end_at,
            slice_days=request.slice_days,
            outcome_grace_days=request.outcome_grace_days,
            request_snapshot={
                **request.model_dump(mode="json", exclude={"max_slices_per_call"}),
                "precommitted_spec": spec,
            },
            summary_snapshot={},
            status="running",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(run)
        self.db.flush()

        for item in self._slice_plan(start_at, end_at, request.slice_days, request.outcome_grace_days):
            slice_key = sha256_dict(
                {
                    "corpus_key": corpus_key,
                    "slice_index": item["slice_index"],
                    "start_at": item["start_at"].isoformat(),
                    "end_at": item["end_at"].isoformat(),
                    "evaluation_as_of": item["evaluation_as_of"].isoformat(),
                }
            )
            self.db.add(
                HorizonCalibrationCorpusSlice(
                    slice_key=slice_key,
                    run_id=run.id,
                    slice_index=item["slice_index"],
                    start_at=item["start_at"],
                    end_at=item["end_at"],
                    evaluation_as_of=item["evaluation_as_of"],
                    status="pending",
                    attempt_count=0,
                    meteo_result={},
                    rte_result={},
                    backtest_result={},
                    error="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
        self.db.commit()
        self.db.refresh(run)
        return run

    def _run_slice(
        self,
        user: User,
        row: HorizonCalibrationCorpusSlice,
        request: HorizonCalibrationCorpusBuildRequest,
    ) -> None:
        row.status = "running"
        row.attempt_count += 1
        row.started_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        row.error = ""
        self.db.commit()

        try:
            meteo = HorizonHistoricalBackfillService(self.db).backfill(
                HorizonMeteoFranceArchiveBackfillRequest(
                    start_at=row.start_at,
                    end_at=row.end_at,
                    departments=request.departments,
                    min_color_id=request.meteo_min_color_id,
                    max_snapshots=request.meteo_max_snapshots_per_slice,
                    merge_gap_hours=request.meteo_merge_gap_hours,
                )
            )
            row.meteo_result = meteo
            row.updated_at = datetime.utcnow()
            self.db.commit()

            rte = HorizonRteCoolingLoadBackfillService(self.db).backfill(
                HorizonRteCoolingLoadBackfillRequest(
                    start_at=row.start_at,
                    end_at=row.evaluation_as_of,
                    baseline_lookback_days=request.rte_baseline_lookback_days,
                    minimum_lift_ratio=request.rte_minimum_lift_ratio,
                    minimum_afternoon_points=request.rte_minimum_afternoon_points,
                    max_records=request.rte_max_records_per_slice,
                )
            )
            row.rte_result = rte
            row.updated_at = datetime.utcnow()
            self.db.commit()

            backtest = HorizonCoverageAwareHistoricalBacktestFactory(self.db).run(
                user,
                HorizonHistoricalBacktestRequest(
                    start_at=row.start_at,
                    end_at=row.end_at,
                    evaluation_as_of=row.evaluation_as_of,
                    event_types=["extreme_heat_region"],
                    max_events=request.backtest_max_events,
                    max_cases=request.backtest_max_cases,
                ),
            )
            row.backtest_result = backtest
            row.status = "completed"
            row.completed_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            persisted = self.db.query(HorizonCalibrationCorpusSlice).filter(
                HorizonCalibrationCorpusSlice.id == row.id
            ).one()
            persisted.status = "failed"
            persisted.error = str(exc)[:2000]
            persisted.updated_at = datetime.utcnow()
            self.db.commit()

    def _lead_times(self, slices: list[HorizonCalibrationCorpusSlice]) -> list[float]:
        run_ids = [
            int(item.backtest_result.get("run_id"))
            for item in slices
            if item.status == "completed" and item.backtest_result.get("run_id") is not None
        ]
        if not run_ids:
            return []
        backtest_runs = self.db.query(HorizonHistoricalBacktestRun).filter(
            HorizonHistoricalBacktestRun.id.in_(run_ids)
        ).all()
        forecast_ids = sorted({
            forecast_id
            for run in backtest_runs
            for forecast_id in (run.selected_forecast_ids or [])
        })
        if not forecast_ids:
            return []
        resolutions = self.db.query(HorizonForecastResolution).filter(
            HorizonForecastResolution.forecast_id.in_(forecast_ids),
            HorizonForecastResolution.correctness.in_(["confirmed", "partial"]),
        ).all()
        return sorted(
            float(row.predictive_lead_time_hours)
            for row in resolutions
            if row.predictive_lead_time_hours is not None
        )

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        if len(values) == 1:
            return round(values[0], 3)
        position = (len(values) - 1) * fraction
        low = int(position)
        high = min(low + 1, len(values) - 1)
        weight = position - low
        return round(values[low] * (1.0 - weight) + values[high] * weight, 3)

    def _summary(self, user: User, run: HorizonCalibrationCorpusRun) -> dict:
        slices = self.db.query(HorizonCalibrationCorpusSlice).filter(
            HorizonCalibrationCorpusSlice.run_id == run.id
        ).order_by(HorizonCalibrationCorpusSlice.slice_index.asc()).all()

        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        events_promoted = 0
        events_replayed = 0
        regional_events = 0
        complete_regions = 0
        partial_regions = 0
        selected_cases = 0
        outcomes = {"confirmed": 0, "partial": 0, "false": 0, "inconclusive": 0, "unresolved": 0}
        skipped: dict[str, int] = {}

        for item in slices:
            counts[item.status if item.status in counts else "failed"] += 1
            if item.status != "completed":
                continue
            meteo = item.meteo_result or {}
            rte = item.rte_result or {}
            backtest = item.backtest_result or {}
            events_promoted += int(meteo.get("events_promoted") or 0)
            events_replayed += int(meteo.get("events_replayed") or 0)
            regional_events += int(rte.get("regional_heat_events_considered") or 0)
            for region in rte.get("regions") or []:
                if region.get("coverage_complete"):
                    complete_regions += 1
                else:
                    partial_regions += 1
            selected_cases += int(backtest.get("selected_cases") or 0)
            for key, value in (backtest.get("outcomes") or {}).items():
                if key in outcomes:
                    outcomes[key] += int(value or 0)
            for key, value in (backtest.get("skipped") or {}).items():
                skipped[key] = skipped.get(key, 0) + int(value or 0)

        lead_times = self._lead_times(slices)
        calibration = HorizonEmpiricalCalibrationService(self.db).profile(
            user,
            mode="backtest",
            as_of=run.requested_end_at + timedelta(days=run.outcome_grace_days),
        )
        evidence = calibration["global_binary_evidence"]
        thresholds = calibration["eligibility_thresholds"]
        return {
            "engine": self.ENGINE_VERSION,
            "corpus_spec_version": self.CORPUS_SPEC_VERSION,
            "run_id": run.id,
            "corpus_key": run.corpus_key,
            "window": {
                "start_at": run.requested_start_at.isoformat(),
                "end_at": run.requested_end_at.isoformat(),
                "outcome_grace_days": run.outcome_grace_days,
            },
            "slices": {"total": len(slices), **counts},
            "evidence_yield": {
                "meteofrance_events_promoted": events_promoted,
                "meteofrance_events_replayed": events_replayed,
                "regional_heat_events_considered": regional_events,
                "rte_region_windows_complete": complete_regions,
                "rte_region_windows_partial": partial_regions,
                "forecastable_cases": selected_cases,
                "outcomes": outcomes,
                "skipped": skipped,
            },
            "lead_time_distribution_hours": {
                "count": len(lead_times),
                "min": round(min(lead_times), 3) if lead_times else None,
                "p50": round(median(lead_times), 3) if lead_times else None,
                "p90": self._percentile(lead_times, 0.90),
                "max": round(max(lead_times), 3) if lead_times else None,
            },
            "calibration": calibration,
            "readiness_distance": {
                "binary_labels_missing": max(0, thresholds["global_binary_labels"] - evidence["binary_labels"]),
                "distinct_events_missing": max(0, thresholds["global_distinct_events"] - evidence["distinct_events"]),
                "has_success": evidence["successes"] > 0,
                "has_failure": evidence["failures"] > 0,
                "global_gate_ready": calibration["probability_calibration_ready"],
                "probability_emission_enabled": False,
            },
            "critical_semantics": {
                "thresholds_precommitted_before_scoring": True,
                "corpus_builder_tunes_thresholds_from_results": False,
                "failed_slice_is_negative_evidence": False,
                "partial_coverage_authorizes_negative_label": False,
                "windy_historical_forecasts_fabricated": False,
                "numeric_probabilities_enabled": False,
            },
        }

    def build(self, user: User, request: HorizonCalibrationCorpusBuildRequest) -> dict:
        start_at = _utc_naive(request.start_at)
        end_at = _utc_naive(request.end_at)
        now = datetime.utcnow()
        if start_at < METEOFRANCE_ARCHIVE_AVAILABLE_FROM:
            raise ValueError("calibration corpus starts at Météo-France archive availability: 2022-11-28")
        if end_at + timedelta(days=request.outcome_grace_days) > now + timedelta(minutes=5):
            raise ValueError("corpus end_at must leave the full historical outcome-grace window in the past")

        run = self._get_or_create_run(user, request)
        slices = self.db.query(HorizonCalibrationCorpusSlice).filter(
            HorizonCalibrationCorpusSlice.run_id == run.id,
            HorizonCalibrationCorpusSlice.status != "completed",
        ).order_by(
            HorizonCalibrationCorpusSlice.slice_index.asc()
        ).limit(request.max_slices_per_call).all()

        processed = 0
        for row in slices:
            self._run_slice(user, row, request)
            processed += 1

        all_slices = self.db.query(HorizonCalibrationCorpusSlice).filter(
            HorizonCalibrationCorpusSlice.run_id == run.id
        ).all()
        if all(item.status == "completed" for item in all_slices):
            run.status = "completed"
        elif any(item.status == "completed" for item in all_slices):
            run.status = "partial"
        elif any(item.status == "failed" for item in all_slices):
            run.status = "partial"
        else:
            run.status = "running"
        summary = self._summary(user, run)
        run.summary_snapshot = summary
        run.updated_at = datetime.utcnow()
        self.db.commit()
        return {
            **summary,
            "status": run.status,
            "slices_processed_this_call": processed,
            "resume_required": run.status != "completed",
            "replayed_existing_completed_corpus": processed == 0 and run.status == "completed",
        }

    def get_run(self, user: User, run_id: int) -> dict:
        run = self.db.query(HorizonCalibrationCorpusRun).filter(
            HorizonCalibrationCorpusRun.id == run_id,
            HorizonCalibrationCorpusRun.user_id == user.id,
        ).one_or_none()
        if run is None:
            raise ValueError("calibration corpus run not found")
        summary = self._summary(user, run)
        return {**summary, "status": run.status}

    def list_runs(self, user: User, limit: int = 50) -> list[dict]:
        rows = self.db.query(HorizonCalibrationCorpusRun).filter(
            HorizonCalibrationCorpusRun.user_id == user.id
        ).order_by(
            HorizonCalibrationCorpusRun.updated_at.desc(), HorizonCalibrationCorpusRun.id.desc()
        ).limit(limit).all()
        return [
            {
                "run_id": row.id,
                "corpus_key": row.corpus_key,
                "engine": row.engine_version,
                "status": row.status,
                "start_at": row.requested_start_at,
                "end_at": row.requested_end_at,
                "slice_days": row.slice_days,
                "outcome_grace_days": row.outcome_grace_days,
                "summary": row.summary_snapshot,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
