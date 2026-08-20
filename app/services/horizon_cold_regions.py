from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..horizon_models import HorizonGlobalEvent
from .horizon_heat_regions import (
    APPROVED_METEOFRANCE_EVENT_SOURCES,
    DEPARTMENT_TO_REGION,
    REGIONS,
    _parse,
    _utc_naive,
)
from .policy import sha256_dict


class HorizonRegionalColdService:
    ENGINE_VERSION = "horizon-regional-cold-aggregation-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _department(event: HorizonGlobalEvent) -> str | None:
        normalized = (event.raw_facts or {}).get("normalized_facts") or {}
        if isinstance(normalized, dict):
            for key in ("department", "domain_id"):
                value = str(normalized.get(key) or "").upper().strip()
                if value in DEPARTMENT_TO_REGION:
                    return value
        for item in event.geography or []:
            value = str(item).upper().strip()
            if value in DEPARTMENT_TO_REGION:
                return value
        return None

    @staticmethod
    def _validity(event: HorizonGlobalEvent) -> tuple[datetime, datetime] | None:
        normalized = (event.raw_facts or {}).get("normalized_facts") or {}
        if not isinstance(normalized, dict):
            return None
        start = _parse(normalized.get("episode_start"))
        end = _parse(normalized.get("episode_end"))
        if start is not None and end is not None and end > start:
            return start, end
        period = normalized.get("period") or {}
        if isinstance(period, dict):
            start = _parse(period.get("begin_validity_time"))
            end = _parse(period.get("end_validity_time"))
            if start is not None and end is not None and end > start:
                return start, end
        return None

    def aggregate(self, *, start_at: datetime, end_at: datetime, merge_gap_hours: int = 24) -> dict:
        start_at = _utc_naive(start_at)
        end_at = _utc_naive(end_at)
        if end_at <= start_at:
            raise ValueError("regional cold aggregation end_at must be after start_at")
        gap = timedelta(hours=max(0, min(int(merge_gap_hours), 72)))
        department_events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == "extreme_cold",
                HorizonGlobalEvent.source.in_(APPROVED_METEOFRANCE_EVENT_SOURCES),
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at <= end_at,
            )
            .order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .all()
        )

        by_region: dict[str, list[dict]] = defaultdict(list)
        for event in department_events:
            department = self._department(event)
            validity = self._validity(event)
            if department is None or validity is None:
                continue
            region_code = DEPARTMENT_TO_REGION.get(department)
            if region_code is None:
                continue
            validity_start, validity_end = validity
            if validity_end < start_at or validity_start > end_at:
                continue
            by_region[region_code].append({
                "event": event,
                "department": department,
                "start": validity_start,
                "end": validity_end,
            })

        created_ids: list[int] = []
        replayed_ids: list[int] = []
        skipped_single_department = 0
        for region_code, rows in sorted(by_region.items()):
            rows.sort(key=lambda item: (item["start"], item["event"].first_observed_at, item["event"].id))
            clusters: list[list[dict]] = []
            current: list[dict] = []
            current_end: datetime | None = None
            for item in rows:
                if not current or current_end is None or item["start"] > current_end + gap:
                    if current:
                        clusters.append(current)
                    current = [item]
                    current_end = item["end"]
                else:
                    current.append(item)
                    current_end = max(current_end, item["end"])
            if current:
                clusters.append(current)

            region_name = REGIONS[region_code][0]
            for cluster in clusters:
                departments = sorted({item["department"] for item in cluster})
                if len(departments) < 2:
                    skipped_single_department += 1
                    continue
                member_events = sorted(
                    {item["event"].id: item["event"] for item in cluster}.values(),
                    key=lambda event: (event.first_observed_at, event.id),
                )
                member_ids = [event.id for event in member_events]
                first_known_by_department: dict[str, datetime] = {}
                for item in cluster:
                    event_time = _utc_naive(item["event"].first_observed_at)
                    previous = first_known_by_department.get(item["department"])
                    if previous is None or event_time < previous:
                        first_known_by_department[item["department"]] = event_time
                became_regional_at = sorted(first_known_by_department.values())[1]
                episode_start = min(item["start"] for item in cluster)
                episode_end = max(item["end"] for item in cluster)
                member_sources = sorted({event.source for event in member_events})
                key = "regional-cold-" + sha256_dict({
                    "engine": self.ENGINE_VERSION,
                    "region_code": region_code,
                    "member_event_ids": member_ids,
                    "episode_start": episode_start.isoformat(),
                    "episode_end": episode_end.isoformat(),
                })[:48]
                existing = self.db.query(HorizonGlobalEvent).filter(
                    HorizonGlobalEvent.event_key == key
                ).one_or_none()
                if existing is not None:
                    replayed_ids.append(existing.id)
                    continue
                row = HorizonGlobalEvent(
                    event_key=key,
                    event_type="extreme_cold_region",
                    title=f"Vigilance grand froid multi-départements — {region_name}",
                    summary=(
                        "État régional dérivé de plusieurs vigilances grand froid départementales officielles. "
                        "Il ne constitue pas une nouvelle observation météo indépendante."
                    ),
                    geography=["FR", f"REGION:{region_code}"],
                    source="meteofrance-vigilance-derived",
                    source_url="https://vigilance.meteofrance.fr/fr",
                    source_reliability=min(float(event.source_reliability) for event in member_events),
                    raw_facts={
                        "derived_fact": True,
                        "derivation_engine": self.ENGINE_VERSION,
                        "region_code": region_code,
                        "region_name": region_name,
                        "departments": departments,
                        "member_event_ids": member_ids,
                        "member_sources": member_sources,
                        "episode_start": episode_start.isoformat(),
                        "episode_end": episode_end.isoformat(),
                        "regional_condition_requires_distinct_departments": 2,
                        "first_observed_at_basis": "second_distinct_department_first_observed_at",
                        "causal_claim": False,
                    },
                    occurred_at=became_regional_at,
                    first_observed_at=became_regional_at,
                    status="active",
                )
                self.db.add(row)
                self.db.flush()
                created_ids.append(row.id)
        self.db.commit()
        return {
            "engine": self.ENGINE_VERSION,
            "department_events_scanned": len(department_events),
            "regional_events_created": len(created_ids),
            "regional_event_ids": created_ids,
            "regional_events_replayed": len(set(replayed_ids)),
            "replayed_event_ids": sorted(set(replayed_ids)),
            "skipped_single_department_clusters": skipped_single_department,
            "critical_semantics": {
                "regional_event_is_independent_weather_source": False,
                "accepted_member_sources": sorted(APPROVED_METEOFRANCE_EVENT_SOURCES),
                "minimum_distinct_departments": 2,
                "first_observed_at_uses_second_distinct_department": True,
                "duplicate_snapshots_same_department_advance_regional_clock": False,
                "causal_claim": False,
            },
        }
