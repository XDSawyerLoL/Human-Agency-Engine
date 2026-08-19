from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalCoverageInterval
from ..horizon_models import HorizonGlobalEvent
from ..horizon_source_models import HorizonSource
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class HorizonHistoricalCoverageService:
    ENGINE_VERSION = "horizon-historical-coverage-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _scope_matches(row: HorizonHistoricalCoverageInterval, event: HorizonGlobalEvent) -> bool:
        event_types = {str(item) for item in (row.event_types or [])}
        if event_types and "*" not in event_types and event.event_type not in event_types:
            return False

        coverage_geo = {str(item).upper() for item in (row.geography or [])}
        event_geo = {str(item).upper() for item in (event.geography or [])}
        if "*" in coverage_geo:
            return True
        if not event_geo:
            return not coverage_geo
        return event_geo.issubset(coverage_geo)

    @staticmethod
    def _intervals_cover(intervals: list[tuple[datetime, datetime]], start_at: datetime, end_at: datetime) -> bool:
        if end_at <= start_at:
            return False
        cursor = start_at
        for raw_start, raw_end in sorted(intervals, key=lambda item: (item[0], item[1])):
            interval_start = _utc_naive(raw_start)
            interval_end = _utc_naive(raw_end)
            if interval_end < cursor:
                continue
            if interval_start > cursor:
                return False
            if interval_end > cursor:
                cursor = interval_end
            if cursor >= end_at:
                return True
        return False

    def signal_coverage(
        self,
        event: HorizonGlobalEvent,
        signal_types: set[str],
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> dict:
        start_at = _utc_naive(start_at)
        end_at = _utc_naive(end_at)
        required = sorted({str(item) for item in signal_types if str(item).strip()})
        if not required:
            return {
                "complete": False,
                "required_signal_types": [],
                "covered_signal_types": [],
                "missing_signal_types": [],
                "reason": "pattern_has_no_observable_materialization_signal_types",
            }

        rows = (
            self.db.query(HorizonHistoricalCoverageInterval)
            .filter(
                HorizonHistoricalCoverageInterval.coverage_kind == "signal",
                HorizonHistoricalCoverageInterval.completeness == "complete",
                HorizonHistoricalCoverageInterval.start_at <= end_at,
                HorizonHistoricalCoverageInterval.end_at >= start_at,
            )
            .order_by(HorizonHistoricalCoverageInterval.start_at.asc(), HorizonHistoricalCoverageInterval.id.asc())
            .all()
        )
        rows = [row for row in rows if self._scope_matches(row, event)]

        covered = []
        evidence: dict[str, list[int]] = {}
        for signal_type in required:
            intervals = []
            ids = []
            for row in rows:
                declared = {str(item) for item in (row.signal_types or [])}
                if "*" not in declared and signal_type not in declared:
                    continue
                intervals.append((row.start_at, row.end_at))
                ids.append(row.id)
            if self._intervals_cover(intervals, start_at, end_at):
                covered.append(signal_type)
                evidence[signal_type] = ids

        missing = sorted(set(required) - set(covered))
        return {
            "engine": self.ENGINE_VERSION,
            "complete": not missing,
            "required_signal_types": required,
            "covered_signal_types": sorted(covered),
            "missing_signal_types": missing,
            "window": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            "coverage_interval_ids_by_signal": evidence,
            "negative_label_authorized": not missing,
            "absence_of_signal_without_coverage_means_non_occurrence": False,
        }

    def record_interval(
        self,
        source: HorizonSource,
        *,
        coverage_kind: str,
        event_types: list[str],
        signal_types: list[str],
        geography: list[str],
        start_at: datetime,
        end_at: datetime,
        completeness: str,
        basis: str,
        provenance: dict | None = None,
    ) -> HorizonHistoricalCoverageInterval:
        start_at = _utc_naive(start_at)
        end_at = _utc_naive(end_at)
        if end_at <= start_at:
            raise ValueError("coverage end_at must be after start_at")
        if coverage_kind not in {"event", "signal"}:
            raise ValueError("coverage_kind must be event or signal")
        if completeness not in {"complete", "partial"}:
            raise ValueError("coverage completeness must be complete or partial")
        payload = {
            "engine": self.ENGINE_VERSION,
            "source_id": source.id,
            "coverage_kind": coverage_kind,
            "event_types": sorted(set(event_types)),
            "signal_types": sorted(set(signal_types)),
            "geography": sorted({str(item).upper() for item in geography}),
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "completeness": completeness,
            "basis": basis,
            "provenance": provenance or {},
        }
        coverage_key = sha256_dict(payload)
        existing = self.db.query(HorizonHistoricalCoverageInterval).filter(
            HorizonHistoricalCoverageInterval.coverage_key == coverage_key
        ).one_or_none()
        if existing is not None:
            return existing
        row = HorizonHistoricalCoverageInterval(
            coverage_key=coverage_key,
            source_id=source.id,
            coverage_kind=coverage_kind,
            event_types=payload["event_types"],
            signal_types=payload["signal_types"],
            geography=payload["geography"],
            start_at=start_at,
            end_at=end_at,
            completeness=completeness,
            basis=basis,
            provenance=provenance or {},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_intervals(self, *, limit: int = 200) -> list[dict]:
        rows = (
            self.db.query(HorizonHistoricalCoverageInterval, HorizonSource)
            .join(HorizonSource, HorizonSource.id == HorizonHistoricalCoverageInterval.source_id)
            .order_by(HorizonHistoricalCoverageInterval.start_at.desc(), HorizonHistoricalCoverageInterval.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": row.id,
                "coverage_key": row.coverage_key,
                "source_key": source.source_key,
                "coverage_kind": row.coverage_kind,
                "event_types": row.event_types,
                "signal_types": row.signal_types,
                "geography": row.geography,
                "start_at": row.start_at.isoformat(),
                "end_at": row.end_at.isoformat(),
                "completeness": row.completeness,
                "basis": row.basis,
                "provenance": row.provenance,
                "created_at": row.created_at.isoformat(),
            }
            for row, source in rows
        ]
