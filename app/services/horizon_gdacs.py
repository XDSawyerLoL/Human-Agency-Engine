from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..horizon_global_alert_schemas import HorizonGdacsPollRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


GDACS_SEARCH_ENDPOINT = "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/SEARCH"
GDACS_EVENT_TYPE_MAP = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "WF": "wildfire",
    "DR": "drought",
}


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        parsed = None
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y%m%d%H%M%S",
                "%a, %d %b %Y %H:%M:%S %Z",
            ):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("features", "events", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _properties(item: dict) -> dict:
    value = item.get("properties")
    return value if isinstance(value, dict) else item


def _geography(props: dict) -> list[str]:
    values: list[str] = []
    for key in ("iso3", "country", "countryname", "countryName"):
        value = props.get(key)
        if isinstance(value, list):
            values.extend(str(item).upper().strip() for item in value if str(item).strip())
        elif value:
            values.append(str(value).upper().strip())
    return list(dict.fromkeys(values))


def _provider_updated_at(props: dict) -> datetime | None:
    for key in ("datetime", "dateadded", "dateAdded", "todate", "toDate"):
        parsed = _parse_datetime(props.get(key))
        if parsed is not None:
            return parsed
    return None


def _event_time(props: dict, fallback: datetime | None) -> datetime | None:
    for key in ("fromdate", "fromDate", "date", "eventdate", "eventDate"):
        parsed = _parse_datetime(props.get(key))
        if parsed is not None:
            return parsed
    return fallback


class HorizonGdacsService:
    ENGINE_VERSION = "horizon-gdacs-source-intelligence-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key="gdacs-official",
                name="Global Disaster Alert and Coordination System",
                source_class="official_multilateral",
                adapter_kind="gdacs_events_geojson_v1",
                domains=["disasters", "multi_hazard", "global_events", "historical_archive"],
                geography=["*"],
                base_locator=GDACS_SEARCH_ENDPOINT,
                trust_weight=0.90,
                refresh_seconds=900,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "multilateral_disaster_detection_and_corroboration",
                    "evidence_roles": ["precursor", "confirmation", "physical_state"],
                    "independence_family": "gdacs",
                    "provider": "Global Disaster Alert and Coordination System, GDACS",
                    "api_version": "v1",
                    "format": "GeoJSON_or_JSON",
                    "historical_search_available": True,
                    "adapter_direct_event_promotion": False,
                },
            )
        )
        if not source.enabled:
            raise ValueError("GDACS source is disabled")
        return source

    @staticmethod
    def parse_payload(payload: Any) -> list[dict]:
        parsed: list[dict] = []
        for item in _records(payload):
            props = _properties(item)
            event_code = str(
                props.get("eventtype")
                or props.get("eventType")
                or props.get("type")
                or ""
            ).upper().strip()
            event_id = props.get("eventid") or props.get("eventId") or props.get("id")
            episode_id = props.get("episodeid") or props.get("episodeId") or props.get("episode")
            if not event_code or event_id is None:
                continue
            updated_at = _provider_updated_at(props)
            occurred_at = _event_time(props, updated_at)
            alert_level = str(props.get("alertlevel") or props.get("alertLevel") or "").lower().strip()
            title = str(
                props.get("name")
                or props.get("eventname")
                or props.get("eventName")
                or props.get("description")
                or f"GDACS {event_code} {event_id}"
            ).strip()
            summary = str(
                props.get("description")
                or props.get("htmldescription")
                or props.get("htmlDescription")
                or title
            )
            geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else None
            snapshot_fingerprint = sha256_dict({"properties": props, "geometry": geometry})
            parsed.append({
                "event_code": event_code,
                "event_type": GDACS_EVENT_TYPE_MAP.get(event_code, f"gdacs_{event_code.lower()}"),
                "event_id": str(event_id),
                "episode_id": str(episode_id) if episode_id is not None else None,
                "canonical_event_id": f"GDACS:{event_code}:{event_id}",
                "alert_level": alert_level,
                "title": title[:255],
                "summary": summary,
                "geography": _geography(props),
                "provider_updated_at": updated_at,
                "occurred_at": occurred_at,
                "geometry": geometry,
                "properties": props,
                "snapshot_fingerprint": snapshot_fingerprint,
                "source_url": str(
                    props.get("url")
                    or props.get("link")
                    or f"https://www.gdacs.org/resources.aspx?eventid={event_id}&eventtype={event_code}"
                ),
            })
        return parsed

    def _fetch_page(
        self,
        client: httpx.Client,
        request: HorizonGdacsPollRequest,
        *,
        from_date: str,
        to_date: str,
        page_number: int,
    ) -> list[dict]:
        response = client.get(
            GDACS_SEARCH_ENDPOINT,
            params={
                "eventlist": ";".join(request.event_types),
                "fromdate": from_date,
                "todate": to_date,
                "alertlevel": ";".join(request.alert_levels),
                "pagesize": request.page_size,
                "pagenumber": page_number,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("GDACS response is not valid JSON") from exc
        return self.parse_payload(payload)

    def poll(
        self,
        request: HorizonGdacsPollRequest,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        source = self._source()
        fetched_at = observed_at or datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        to_date = fetched_at.date().isoformat()
        from_date = (fetched_at - timedelta(days=request.lookback_days)).date().isoformat()
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(25.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json,application/geo+json"},
            )

        rows: list[dict] = []
        pages_fetched = 0
        try:
            for page_number in range(1, request.max_pages + 1):
                page = self._fetch_page(
                    client,
                    request,
                    from_date=from_date,
                    to_date=to_date,
                    page_number=page_number,
                )
                pages_fetched += 1
                rows.extend(page)
                if len(page) < request.page_size:
                    break
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"GDACS poll failed: {str(exc)[:300]}") from exc
        finally:
            if owned_client:
                client.close()

        service = HorizonSourceService(self.db)
        created_ids: list[int] = []
        replayed_ids: list[int] = []
        canonical_ids: set[str] = set()
        for item in rows:
            event_code = item["event_code"]
            event_id = item["event_id"]
            episode_id = item["episode_id"] or "0"
            canonical_ids.add(item["canonical_event_id"])
            external_key = (
                f"gdacs:{event_code}:{event_id}:{episode_id}:{item['snapshot_fingerprint'][:24]}"
            )[:192]
            existing = self.db.query(HorizonRawObservation).filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.external_key == external_key,
            ).one_or_none()
            if existing is not None:
                replayed_ids.append(existing.id)
                continue
            observation = HorizonObservationIngest(
                external_key=external_key,
                observation_type="multilateral_disaster_alert_snapshot",
                title=item["title"],
                summary=item["summary"],
                source_url=item["source_url"],
                geography=item["geography"],
                canonical_facts={
                    "provider": "GDACS",
                    "canonical_event_id": item["canonical_event_id"],
                    "event_code": event_code,
                    "normalized_event_type_hint": item["event_type"],
                    "event_id": event_id,
                    "episode_id": item["episode_id"],
                    "alert_level": item["alert_level"],
                    "severity": item["properties"].get("severity"),
                    "population": item["properties"].get("population"),
                    "provider_updated_at": (
                        item["provider_updated_at"].isoformat() if item["provider_updated_at"] else None
                    ),
                },
                raw_metadata={
                    "engine": self.ENGINE_VERSION,
                    "provider_properties": item["properties"],
                    "geometry": item["geometry"],
                    "snapshot_fingerprint": item["snapshot_fingerprint"],
                    "attribution": "Global Disaster Alert and Coordination System, GDACS",
                    "adapter_direct_event_promotion": False,
                },
                event_time=item["occurred_at"],
                published_at=item["provider_updated_at"],
                observed_at=fetched_at,
            )
            row, _ = service.ingest_observation(source, observation)
            created_ids.append(row.id)

        return {
            "engine": self.ENGINE_VERSION,
            "source_key": source.source_key,
            "window": {"from_date": from_date, "to_date": to_date},
            "pages_fetched": pages_fetched,
            "provider_records_parsed": len(rows),
            "canonical_events_seen": len(canonical_ids),
            "new_observations": len(set(created_ids)),
            "replayed_observations": len(set(replayed_ids)),
            "observation_ids": sorted(set(created_ids + replayed_ids)),
            "critical_semantics": {
                "adapter_creates_confirmed_event": False,
                "source_is_official_primary": False,
                "source_class": "official_multilateral",
                "provider_timestamp_preserved": True,
                "fetch_time_separate_from_provider_time": True,
                "alert_level_is_probability": False,
            },
        }
