from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_models import HorizonGlobalEvent
from .policy import sha256_dict


REGIONS: dict[str, tuple[str, set[str]]] = {
    "11": ("Île-de-France", {"75", "77", "78", "91", "92", "93", "94", "95"}),
    "24": ("Centre-Val de Loire", {"18", "28", "36", "37", "41", "45"}),
    "27": ("Bourgogne-Franche-Comté", {"21", "25", "39", "58", "70", "71", "89", "90"}),
    "28": ("Normandie", {"14", "27", "50", "61", "76"}),
    "32": ("Hauts-de-France", {"02", "59", "60", "62", "80"}),
    "44": ("Grand Est", {"08", "10", "51", "52", "54", "55", "57", "67", "68", "88"}),
    "52": ("Pays de la Loire", {"44", "49", "53", "72", "85"}),
    "53": ("Bretagne", {"22", "29", "35", "56"}),
    "75": ("Nouvelle-Aquitaine", {"16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"}),
    "76": ("Occitanie", {"09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"}),
    "84": ("Auvergne-Rhône-Alpes", {"01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"}),
    "93": ("Provence-Alpes-Côte d’Azur", {"04", "05", "06", "13", "83", "84"}),
    "94": ("Corse", {"2A", "2B"}),
}

DEPARTMENT_TO_REGION = {
    department: code
    for code, (_, departments) in REGIONS.items()
    for department in departments
}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_naive(parsed)


class HorizonRegionalHeatService:
    ENGINE_VERSION = "horizon-regional-heat-aggregation-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _department(event: HorizonGlobalEvent) -> str | None:
        normalized = (event.raw_facts or {}).get("normalized_facts") or {}
        if isinstance(normalized, dict):
            value = str(normalized.get("department") or "").upper().strip()
            if value:
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
        if start is None or end is None or end <= start:
            return None
        return start, end

    def aggregate(self, *, start_at: datetime, end_at: datetime, merge_gap_hours: int = 24) -> dict:
        start_at = _utc_naive(start_at)
        end_at = _utc_naive(end_at)
        if end_at <= start_at:
            raise ValueError("regional heat aggregation end_at must be after start_at")
        gap = timedelta(hours=max(0, min(int(merge_gap_hours), 72)))
        department_events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == "extreme_heat",
                HorizonGlobalEvent.source == "meteofrance-vigilance-archive",
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
            by_region[region_code].append(
                {
                    "event": event,
                    "department": department,
                    "start": validity_start,
                    "end": validity_end,
                }
            )

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
                known_times = sorted(event.first_observed_at for event in member_events)
                became_regional_at = known_times[1]
                episode_start = min(item["start"] for item in cluster)
                episode_end = max(item["end"] for item in cluster)
                key = "regional-heat-" + sha256_dict(
                    {
                        "engine": self.ENGINE_VERSION,
                        "region_code": region_code,
                        "member_event_ids": member_ids,
                        "episode_start": episode_start.isoformat(),
                        "episode_end": episode_end.isoformat(),
                    }
                )[:48]
                existing = self.db.query(HorizonGlobalEvent).filter(
                    HorizonGlobalEvent.event_key == key
                ).one_or_none()
                if existing is not None:
                    replayed_ids.append(existing.id)
                    continue
                row = HorizonGlobalEvent(
                    event_key=key,
                    event_type="extreme_heat_region",
                    title=f"Vigilance canicule multi-départements — {region_name}",
                    summary=(
                        "État régional dérivé de plusieurs vigilances canicule départementales officielles. "
                        "Il ne constitue pas une nouvelle observation météo indépendante."
                    ),
                    geography=["FR", f"REGION:{region_code}"],
                    source="meteofrance-vigilance-archive",
                    source_url="https://vigilance.meteofrance.fr/fr",
                    source_reliability=min(float(event.source_reliability) for event in member_events),
                    raw_facts={
                        "derived_fact": True,
                        "derivation_engine": self.ENGINE_VERSION,
                        "region_code": region_code,
                        "region_name": region_name,
                        "departments": departments,
                        "member_event_ids": member_ids,
                        "episode_start": episode_start.isoformat(),
                        "episode_end": episode_end.isoformat(),
                        "regional_condition_requires_distinct_departments": 2,
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
                "minimum_distinct_departments": 2,
                "first_observed_at_uses_second_known_department": True,
                "causal_claim": False,
            },
        }
