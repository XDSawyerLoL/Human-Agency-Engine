from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..horizon_collector_models import HorizonCollectorLease
from ..horizon_corpus_models import HorizonCalibrationCorpusRun
from ..horizon_corpus_schemas import HorizonCalibrationCorpusBuildRequest
from ..models import User
from .horizon_corpus import HorizonCalibrationCorpusService


class HorizonCorpusWorkerService:
    ENGINE_VERSION = "horizon-calibration-corpus-worker-v0.1"
    LEASE_KEY = "horizon-calibration-corpus-worker"

    def __init__(self, db: Session):
        self.db = db

    def acquire_lease(self, owner_id: str, *, lease_seconds: int) -> dict:
        now = datetime.utcnow()
        row = (
            self.db.query(HorizonCollectorLease)
            .filter(HorizonCollectorLease.collector_key == self.LEASE_KEY)
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            row = HorizonCollectorLease(
                collector_key=self.LEASE_KEY,
                owner_id=owner_id,
                acquired_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
            self.db.add(row)
            self.db.commit()
            return {"acquired": True, "owner_id": owner_id, "lease_expires_at": row.lease_expires_at}
        if row.owner_id != owner_id and row.lease_expires_at > now:
            self.db.rollback()
            return {"acquired": False, "owner_id": row.owner_id, "lease_expires_at": row.lease_expires_at}
        if row.owner_id != owner_id:
            row.acquired_at = now
        row.owner_id = owner_id
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.updated_at = now
        self.db.commit()
        return {"acquired": True, "owner_id": owner_id, "lease_expires_at": row.lease_expires_at}

    def heartbeat(self, owner_id: str, *, lease_seconds: int) -> None:
        now = datetime.utcnow()
        row = self.db.query(HorizonCollectorLease).filter(
            HorizonCollectorLease.collector_key == self.LEASE_KEY,
            HorizonCollectorLease.owner_id == owner_id,
        ).one_or_none()
        if row is None:
            return
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.updated_at = now
        self.db.commit()

    def run_once(
        self,
        *,
        owner_id: str,
        lease_seconds: int = 7200,
        max_runs: int = 1,
        slices_per_run: int = 1,
    ) -> dict:
        lease = self.acquire_lease(owner_id, lease_seconds=lease_seconds)
        if not lease["acquired"]:
            return {
                "engine": self.ENGINE_VERSION,
                "status": "standby",
                "leader": lease,
                "numeric_probabilities_enabled": False,
            }

        runs = (
            self.db.query(HorizonCalibrationCorpusRun)
            .filter(HorizonCalibrationCorpusRun.status != "completed")
            .order_by(HorizonCalibrationCorpusRun.updated_at.asc(), HorizonCalibrationCorpusRun.id.asc())
            .limit(max_runs)
            .all()
        )
        if not runs:
            self.heartbeat(owner_id, lease_seconds=lease_seconds)
            return {
                "engine": self.ENGINE_VERSION,
                "status": "idle",
                "pending_runs": 0,
                "numeric_probabilities_enabled": False,
            }

        results = []
        for run in runs:
            user = self.db.query(User).filter(User.id == run.user_id).one_or_none()
            if user is None:
                results.append({"run_id": run.id, "status": "failed", "error": "corpus user not found"})
                continue
            payload = dict(run.request_snapshot or {})
            payload.pop("precommitted_spec", None)
            payload["max_slices_per_call"] = slices_per_run
            try:
                request = HorizonCalibrationCorpusBuildRequest.model_validate(payload)
                result = HorizonCalibrationCorpusService(self.db).build(user, request)
                results.append({
                    "run_id": run.id,
                    "status": result["status"],
                    "slices_processed": result["slices_processed_this_call"],
                    "resume_required": result["resume_required"],
                    "readiness_distance": result["readiness_distance"],
                })
            except Exception as exc:
                self.db.rollback()
                results.append({"run_id": run.id, "status": "failed", "error": str(exc)[:1500]})
            self.heartbeat(owner_id, lease_seconds=lease_seconds)

        return {
            "engine": self.ENGINE_VERSION,
            "status": "completed" if all(item["status"] != "failed" for item in results) else "partial",
            "runs_considered": len(runs),
            "results": results,
            "critical_semantics": {
                "historical_work_is_rate_separated_from_live_collection": True,
                "one_slice_per_run_by_default": True,
                "failed_acquisition_is_negative_evidence": False,
                "numeric_probabilities_enabled": False,
            },
        }
