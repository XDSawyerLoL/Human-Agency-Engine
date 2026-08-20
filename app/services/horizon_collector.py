from __future__ import annotations

import json
from datetime import datetime, timedelta
from time import monotonic
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..config import settings
from ..horizon_behavioral_signal_schemas import HorizonMediaAttentionRefreshRequest
from ..horizon_collector_models import (
    HorizonCollectorCycle,
    HorizonCollectorLease,
    HorizonCollectorSourceState,
)
from ..horizon_convergence_schemas import (
    HorizonLiveConvergencePollRequest,
    HorizonRteRealtimePollRequest,
    HorizonWindyPoint,
)
from ..horizon_emerging_schemas import HorizonEmergingClusterRequest
from ..horizon_expiry_schemas import HorizonForecastExpiryScanRequest
from ..horizon_global_alert_schemas import HorizonMeteoAlarmPollRequest
from ..horizon_materialization_schemas import HorizonMaterializationScanRequest
from ..horizon_provisional_schemas import HorizonProvisionalReconcileRequest
from ..horizon_reevaluation_schemas import HorizonReevaluationRequest
from ..horizon_warning_schemas import HorizonWarningRefreshRequest
from .horizon_emerging import HorizonEmergingService
from .horizon_expiry import HorizonForecastExpiryService
from .horizon_live_convergence import HorizonLiveConvergenceService
from .horizon_materialization import HorizonMaterializationService
from .horizon_media_attention import HorizonMediaAttentionService
from .horizon_provisional import HorizonProvisionalService
from .horizon_reevaluation import HorizonReevaluationService
from .horizon_response_library import HorizonResponseLibraryService
from .horizon_sources import HorizonSourceService
from .horizon_warning import HorizonWarningService


class HorizonCollectorService:
    ENGINE_VERSION = "horizon-permanent-collector-v0.1"
    COLLECTOR_KEY = "horizon-world-intelligence"
    SOURCE_ORDER = (
        "sncf",
        "vigicrues",
        "meteofrance",
        "meteoalarm",
        "gdelt",
        "gdacs",
        "fuel",
        "rte_realtime",
        "windy",
        "synthesis",
    )
    POLL_SOURCE_NAMES = {
        "gdelt": ("gdelt-doc-2",),
        "gdacs": ("gdacs-official",),
        "meteofrance": ("meteofrance-vigilance",),
        "meteoalarm": ("meteoalarm-atom",),
        "fuel": ("fr-fuel-ruptures-live",),
        "rte_realtime": ("rte-eco2mix-regional-tr",),
        "vigicrues": ("vigicrues-official",),
        "sncf": ("sncf-service-alerts",),
        "windy": ("windy-point-forecast",),
    }

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _csv(value: str) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in str(value or "").split(",") if item.strip()))

    @staticmethod
    def _safe_step(name: str, fn) -> dict:
        try:
            return {"step": name, "ok": True, "result": jsonable_encoder(fn())}
        except Exception as exc:
            return {"step": name, "ok": False, "error": str(exc)[:1000]}

    @property
    def cadence_map(self) -> dict[str, int]:
        return {
            "gdelt": settings.horizon_collector_gdelt_seconds,
            "gdacs": settings.horizon_collector_gdacs_seconds,
            "meteofrance": settings.horizon_collector_meteofrance_seconds,
            "meteoalarm": settings.horizon_collector_meteoalarm_seconds,
            "fuel": settings.horizon_collector_fuel_seconds,
            "rte_realtime": settings.horizon_collector_rte_seconds,
            "vigicrues": settings.horizon_collector_vigicrues_seconds,
            "sncf": settings.horizon_collector_sncf_seconds,
            "windy": settings.horizon_collector_windy_seconds,
            "synthesis": settings.horizon_collector_synthesis_seconds,
        }

    def _ensure_states(self, now: datetime) -> list[HorizonCollectorSourceState]:
        existing = {
            row.source_key: row
            for row in self.db.query(HorizonCollectorSourceState).all()
        }
        for source_key in self.SOURCE_ORDER:
            cadence = int(self.cadence_map[source_key])
            row = existing.get(source_key)
            if row is None:
                row = HorizonCollectorSourceState(
                    source_key=source_key,
                    cadence_seconds=cadence,
                    next_due_at=now,
                    consecutive_failures=0,
                    last_error="",
                    last_result={},
                    updated_at=now,
                )
                self.db.add(row)
                existing[source_key] = row
            elif row.cadence_seconds != cadence:
                row.cadence_seconds = cadence
                row.updated_at = now
        self.db.commit()
        return [existing[key] for key in self.SOURCE_ORDER]

    def acquire_lease(self, owner_id: str, now: datetime | None = None) -> dict:
        now = now or self._now()
        lease = (
            self.db.query(HorizonCollectorLease)
            .filter(HorizonCollectorLease.collector_key == self.COLLECTOR_KEY)
            .with_for_update()
            .one_or_none()
        )
        lease_seconds = int(settings.horizon_collector_lease_seconds)
        if lease is None:
            lease = HorizonCollectorLease(
                collector_key=self.COLLECTOR_KEY,
                owner_id=owner_id,
                acquired_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
            self.db.add(lease)
            self.db.commit()
            return {"acquired": True, "owner_id": owner_id, "lease_expires_at": lease.lease_expires_at}

        if lease.owner_id != owner_id and lease.lease_expires_at > now:
            self.db.rollback()
            return {
                "acquired": False,
                "owner_id": lease.owner_id,
                "lease_expires_at": lease.lease_expires_at,
            }

        if lease.owner_id != owner_id:
            lease.acquired_at = now
        lease.owner_id = owner_id
        lease.heartbeat_at = now
        lease.lease_expires_at = now + timedelta(seconds=lease_seconds)
        lease.updated_at = now
        self.db.commit()
        return {"acquired": True, "owner_id": owner_id, "lease_expires_at": lease.lease_expires_at}

    def heartbeat(self, owner_id: str, now: datetime | None = None) -> None:
        now = now or self._now()
        lease = self.db.query(HorizonCollectorLease).filter(
            HorizonCollectorLease.collector_key == self.COLLECTOR_KEY,
            HorizonCollectorLease.owner_id == owner_id,
        ).one_or_none()
        if lease is None:
            return
        lease.heartbeat_at = now
        lease.lease_expires_at = now + timedelta(seconds=int(settings.horizon_collector_lease_seconds))
        lease.updated_at = now
        self.db.commit()

    def _windy_points(self) -> list[HorizonWindyPoint]:
        raw = str(settings.horizon_collector_windy_points_json or "[]").strip() or "[]"
        value = json.loads(raw)
        if not isinstance(value, list):
            raise ValueError("HORIZON_COLLECTOR_WINDY_POINTS_JSON must be a JSON array")
        return [HorizonWindyPoint.model_validate(item) for item in value]

    def _poll_request(self, due: set[str]) -> HorizonLiveConvergencePollRequest:
        windy_points = self._windy_points() if "windy" in due else []
        return HorizonLiveConvergencePollRequest(
            include_gdelt="gdelt" in due,
            include_gdacs="gdacs" in due,
            include_meteofrance="meteofrance" in due,
            include_meteoalarm="meteoalarm" in due,
            include_fuel="fuel" in due,
            include_rte_realtime="rte_realtime" in due,
            include_vigicrues="vigicrues" in due,
            include_sncf="sncf" in due,
            windy_points=windy_points,
            refresh_provisional_candidates="synthesis" in due,
            snapshot_recent_active_events="synthesis" in due,
            max_active_events=settings.horizon_collector_max_active_events,
            build_event_graph="synthesis" in due,
            event_graph_lookback_hours=settings.horizon_collector_event_graph_lookback_hours,
            meteoalarm=HorizonMeteoAlarmPollRequest(
                all_europe=settings.horizon_collector_meteoalarm_all_europe,
            ),
            rte=HorizonRteRealtimePollRequest(
                region_codes=self._csv(settings.horizon_collector_rte_region_codes),
            ),
        )

    def _external_outcome(self, source_key: str, poll_result: dict) -> dict:
        names = self.POLL_SOURCE_NAMES[source_key]
        entries = []
        for item in poll_result.get("sources", []):
            name = str(item.get("source") or "")
            if any(name == expected or name.startswith(expected + ":") for expected in names):
                entries.append(item)
        if source_key == "windy" and not entries:
            return {
                "source_key": source_key,
                "status": "skipped",
                "reason": "no Windy points configured",
                "entries": [],
            }
        if not entries:
            return {
                "source_key": source_key,
                "status": "failed",
                "reason": "source produced no collector result",
                "entries": [],
            }
        failures = [item for item in entries if item.get("ok") is False and not item.get("skipped")]
        successes = [item for item in entries if item.get("ok") is True]
        skipped = [item for item in entries if item.get("skipped")]
        if failures:
            status = "failed"
            reason = "; ".join(str(item.get("error") or item.get("reason") or "source failed") for item in failures)[:1000]
        elif successes:
            status = "success"
            reason = ""
        elif skipped:
            status = "skipped"
            reason = "; ".join(str(item.get("reason") or "configuration skipped") for item in skipped)[:1000]
        else:
            status = "failed"
            reason = "source returned indeterminate result"
        return {
            "source_key": source_key,
            "status": status,
            "reason": reason,
            "entries": jsonable_encoder(entries),
        }

    def _run_synthesis(self, poll_result: dict) -> dict:
        steps = [
            self._safe_step("response_library_sync", lambda: HorizonResponseLibraryService(self.db).sync_builtins()),
            self._safe_step(
                "gdelt_emerging_cluster",
                lambda: HorizonEmergingService(self.db).cluster_gdelt(
                    HorizonEmergingClusterRequest(bucket_minutes=15, lookback_buckets=4, min_articles=3)
                ),
            ),
            self._safe_step(
                "provisional_reconcile",
                lambda: HorizonProvisionalService(self.db).reconcile(
                    HorizonProvisionalReconcileRequest(max_forecasts=1000)
                ),
            ),
            self._safe_step(
                "media_attention_refresh",
                lambda: HorizonMediaAttentionService(self.db).refresh(HorizonMediaAttentionRefreshRequest()),
            ),
            self._safe_step(
                "warning_refresh",
                lambda: HorizonWarningService(self.db).refresh(
                    HorizonWarningRefreshRequest(max_events=200, recency_hours=72)
                ),
            ),
            self._safe_step(
                "materialization_scan",
                lambda: HorizonMaterializationService(self.db).scan(
                    HorizonMaterializationScanRequest(mode="live", max_forecasts=2000)
                ),
            ),
            self._safe_step(
                "expiry_scan",
                lambda: HorizonForecastExpiryService(self.db).scan(
                    HorizonForecastExpiryScanRequest(mode="live", max_forecasts=2000)
                ),
            ),
            self._safe_step(
                "reevaluation",
                lambda: HorizonReevaluationService(self.db).run(
                    HorizonReevaluationRequest(max_events=200, max_users=5000, material_score_delta=0.12)
                ),
            ),
        ]
        return {
            "status": "success" if all(item["ok"] for item in steps) else "partial",
            "steps": steps,
            "live_convergence_postprocessing": {
                "provisional_refresh": poll_result.get("provisional_refresh"),
                "weather_chain": poll_result.get("weather_chain"),
                "convergence_snapshot_errors": poll_result.get("convergence_snapshot_errors", []),
                "event_graph": poll_result.get("event_graph"),
            },
        }

    def _apply_state_outcome(self, row: HorizonCollectorSourceState, outcome: dict, now: datetime) -> None:
        row.last_attempt_at = now
        row.last_result = jsonable_encoder(outcome)
        row.updated_at = now
        status = outcome.get("status")
        if status == "success":
            row.last_success_at = now
            row.consecutive_failures = 0
            row.last_error = ""
            delay = row.cadence_seconds
        elif status == "skipped":
            row.last_error = str(outcome.get("reason") or "")[:1000]
            delay = row.cadence_seconds
        else:
            row.consecutive_failures += 1
            row.last_error = str(outcome.get("reason") or "collector source failed")[:1000]
            factor = min(8, 2 ** min(max(row.consecutive_failures - 1, 0), 3))
            delay = row.cadence_seconds * factor
        row.next_due_at = now + timedelta(seconds=delay)

    def run_due(
        self,
        *,
        owner_id: str,
        force_sources: list[str] | None = None,
        trigger: str = "worker",
    ) -> dict:
        started_at = self._now()
        lease = self.acquire_lease(owner_id, started_at)
        if not lease["acquired"]:
            return {
                "engine": self.ENGINE_VERSION,
                "status": "standby",
                "leader": lease,
                "numeric_probabilities_enabled": False,
            }

        states = self._ensure_states(started_at)
        forced = set(force_sources or [])
        due_rows = [row for row in states if row.next_due_at <= started_at or row.source_key in forced]
        due_rows = due_rows[: settings.horizon_collector_max_sources_per_cycle]
        if not due_rows:
            self.heartbeat(owner_id, started_at)
            next_due = min((row.next_due_at for row in states), default=None)
            return {
                "engine": self.ENGINE_VERSION,
                "status": "idle",
                "leader": lease,
                "next_due_at": next_due,
                "numeric_probabilities_enabled": False,
            }

        due = {row.source_key for row in due_rows}
        cycle = HorizonCollectorCycle(
            cycle_key=f"collector:{uuid4().hex}",
            owner_id=owner_id,
            trigger=trigger,
            started_at=started_at,
            status="running",
            due_sources=[row.source_key for row in due_rows],
            source_results=[],
            postprocessing={},
            error="",
            created_at=started_at,
        )
        self.db.add(cycle)
        self.db.commit()
        self.db.refresh(cycle)
        clock = monotonic()

        source_outcomes: list[dict] = []
        postprocessing: dict = {}
        try:
            registry = self._safe_step("source_registry_sync", lambda: HorizonSourceService(self.db).sync_builtin_sources())
            request = self._poll_request(due)
            poll_result = HorizonLiveConvergenceService(self.db).poll(request)
            for row in due_rows:
                if row.source_key == "synthesis":
                    postprocessing = self._run_synthesis(poll_result)
                    outcome = {
                        "source_key": "synthesis",
                        "status": postprocessing["status"],
                        "reason": "" if postprocessing["status"] == "success" else "one or more synthesis steps failed",
                        "registry_sync": registry,
                    }
                else:
                    outcome = self._external_outcome(row.source_key, poll_result)
                source_outcomes.append(outcome)
                self._apply_state_outcome(row, outcome, self._now())

            failed = sum(1 for item in source_outcomes if item["status"] == "failed")
            partial = sum(1 for item in source_outcomes if item["status"] == "partial")
            succeeded = sum(1 for item in source_outcomes if item["status"] == "success")
            skipped = sum(1 for item in source_outcomes if item["status"] == "skipped")
            if failed == 0 and partial == 0:
                cycle.status = "success"
            elif succeeded or skipped:
                cycle.status = "partial"
            else:
                cycle.status = "failed"
        except Exception as exc:
            cycle.status = "failed"
            cycle.error = str(exc)[:2000]
            for row in due_rows:
                outcome = {
                    "source_key": row.source_key,
                    "status": "failed",
                    "reason": cycle.error,
                    "entries": [],
                }
                source_outcomes.append(outcome)
                self._apply_state_outcome(row, outcome, self._now())
        finally:
            finished_at = self._now()
            cycle.finished_at = finished_at
            cycle.source_results = jsonable_encoder(source_outcomes)
            cycle.postprocessing = jsonable_encoder(postprocessing)
            cycle.duration_ms = int((monotonic() - clock) * 1000)
            self.db.commit()
            self.heartbeat(owner_id, finished_at)

        return {
            "engine": self.ENGINE_VERSION,
            "cycle_id": cycle.id,
            "cycle_key": cycle.cycle_key,
            "status": cycle.status,
            "due_sources": cycle.due_sources,
            "source_results": cycle.source_results,
            "postprocessing": cycle.postprocessing,
            "duration_ms": cycle.duration_ms,
            "critical_semantics": {
                "single_active_collector_lease": True,
                "source_failures_are_isolated": True,
                "failed_sources_use_bounded_exponential_backoff": True,
                "collection_cadence_is_not_evidence_weight": True,
                "source_count_is_not_truth_vote": True,
                "numeric_probabilities_enabled": False,
            },
        }

    def status(self, *, cycle_limit: int = 20) -> dict:
        lease = self.db.query(HorizonCollectorLease).filter(
            HorizonCollectorLease.collector_key == self.COLLECTOR_KEY
        ).one_or_none()
        states = self._ensure_states(self._now())
        cycles = (
            self.db.query(HorizonCollectorCycle)
            .order_by(HorizonCollectorCycle.started_at.desc(), HorizonCollectorCycle.id.desc())
            .limit(cycle_limit)
            .all()
        )
        return {
            "engine": self.ENGINE_VERSION,
            "lease": None if lease is None else {
                "owner_id": lease.owner_id,
                "acquired_at": lease.acquired_at,
                "heartbeat_at": lease.heartbeat_at,
                "lease_expires_at": lease.lease_expires_at,
            },
            "sources": [
                {
                    "source_key": row.source_key,
                    "cadence_seconds": row.cadence_seconds,
                    "next_due_at": row.next_due_at,
                    "last_attempt_at": row.last_attempt_at,
                    "last_success_at": row.last_success_at,
                    "consecutive_failures": row.consecutive_failures,
                    "last_error": row.last_error,
                }
                for row in states
            ],
            "recent_cycles": [
                {
                    "id": row.id,
                    "cycle_key": row.cycle_key,
                    "owner_id": row.owner_id,
                    "trigger": row.trigger,
                    "started_at": row.started_at,
                    "finished_at": row.finished_at,
                    "status": row.status,
                    "due_sources": row.due_sources,
                    "duration_ms": row.duration_ms,
                    "error": row.error,
                }
                for row in cycles
            ],
            "numeric_probabilities_enabled": False,
        }
