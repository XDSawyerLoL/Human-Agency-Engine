from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..horizon_live_models import HorizonLiveIngestionRecord, HorizonLiveSource
from ..horizon_models import HorizonGlobalEvent
from .policy import sha256_dict


@dataclass(frozen=True)
class LiveEventCandidate:
    source_key: str
    external_key: str
    event_type: str
    title: str
    summary: str
    geography: list[str]
    source_url: str
    source_reliability: float
    occurred_at: datetime
    observed_at: datetime
    raw_facts: dict[str, Any]


_EVENT_TYPE_MAP = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "WF": "wildfire",
    "DR": "drought",
}

_COUNTRY_ISO2 = {
    "france": "FR",
    "belgium": "BE",
    "germany": "DE",
    "spain": "ES",
    "italy": "IT",
    "portugal": "PT",
    "netherlands": "NL",
    "luxembourg": "LU",
    "switzerland": "CH",
    "united-kingdom": "GB",
    "ireland": "IE",
}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: Any, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return _utc_naive(value)
    text = str(value or "").strip()
    if text:
        normalized = text.replace("Z", "+00:00")
        try:
            return _utc_naive(datetime.fromisoformat(normalized))
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return fallback or datetime.utcnow()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _clean_external(value: Any) -> str:
    text = re.sub(r"\s+", "-", str(value or "unknown").strip())
    return text[:150] or "unknown"


class GDACSAdapter:
    source_key = "gdacs"
    source_name = "Global Disaster Alert and Coordination System"
    source_kind = "official_disaster_alert"
    reliability = 0.97

    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint or settings.horizon_gdacs_url

    def fetch(self) -> Any:
        with httpx.Client(timeout=settings.horizon_http_timeout_seconds, follow_redirects=True) as client:
            response = client.get(
                self.endpoint,
                headers={"User-Agent": "Human-Agency-Engine-HORIZON/0.1"},
            )
            response.raise_for_status()
            return response.json()

    def parse(self, payload: Any, *, fetched_at: datetime | None = None) -> list[LiveEventCandidate]:
        fetched_at = fetched_at or datetime.utcnow()
        if isinstance(payload, dict):
            records = payload.get("features") or payload.get("events") or payload.get("data") or []
        elif isinstance(payload, list):
            records = payload
        else:
            records = []

        result: list[LiveEventCandidate] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            props = item.get("properties") if isinstance(item.get("properties"), dict) else item
            event_code = str(
                props.get("eventtype")
                or props.get("eventType")
                or props.get("type")
                or "GDACS"
            ).upper()
            event_id = props.get("eventid") or props.get("eventId") or props.get("id")
            episode_id = props.get("episodeid") or props.get("episodeId") or props.get("episode")
            external_key = ":".join(
                part for part in (event_code, _clean_external(event_id), _clean_external(episode_id) if episode_id else "") if part
            )
            title = str(
                props.get("name")
                or props.get("eventname")
                or props.get("eventName")
                or props.get("description")
                or f"GDACS {event_code} {event_id or ''}"
            ).strip()
            summary = str(
                props.get("description")
                or props.get("htmldescription")
                or props.get("htmlDescription")
                or title
            )
            country = props.get("country") or props.get("countryname") or props.get("countryName") or props.get("iso3")
            if isinstance(country, list):
                geography = [str(value).upper() for value in country if value]
            elif country:
                geography = [str(country).upper()]
            else:
                geography = []

            observed_at = _parse_dt(
                props.get("datetime")
                or props.get("dateadded")
                or props.get("toDate")
                or props.get("todate"),
                fallback=fetched_at,
            )
            occurred_at = _parse_dt(
                props.get("fromDate") or props.get("fromdate") or props.get("date"),
                fallback=observed_at,
            )
            if occurred_at > observed_at:
                occurred_at = observed_at

            alert_level = str(props.get("alertlevel") or props.get("alertLevel") or "").lower()
            raw = {
                "provider": "GDACS",
                "canonical_event_id": str(event_id or external_key),
                "episode_id": str(episode_id) if episode_id is not None else None,
                "event_code": event_code,
                "alert_level": alert_level,
                "severity": props.get("severity"),
                "population": props.get("population"),
                "provider_properties": props,
                "geometry": item.get("geometry") if isinstance(item, dict) else None,
            }
            source_url = str(
                props.get("url")
                or props.get("link")
                or (
                    f"https://www.gdacs.org/resources.aspx?eventid={event_id}&eventtype={event_code}"
                    if event_id
                    else self.endpoint
                )
            )
            result.append(
                LiveEventCandidate(
                    source_key=self.source_key,
                    external_key=external_key,
                    event_type=_EVENT_TYPE_MAP.get(event_code, f"gdacs_{event_code.lower()}"),
                    title=title[:255],
                    summary=summary,
                    geography=geography,
                    source_url=source_url,
                    source_reliability=self.reliability,
                    occurred_at=occurred_at,
                    observed_at=observed_at,
                    raw_facts=raw,
                )
            )
        return result


class MeteoAlarmAtomAdapter:
    source_kind = "official_weather_alert"
    reliability = 0.98

    def __init__(self, country_slug: str):
        self.country_slug = country_slug.strip().lower()
        self.source_key = f"meteoalarm:{self.country_slug}"
        self.source_name = f"MeteoAlarm {self.country_slug}"
        self.endpoint = settings.horizon_meteoalarm_atom_template.format(country=self.country_slug)

    def fetch(self) -> str:
        with httpx.Client(timeout=settings.horizon_http_timeout_seconds, follow_redirects=True) as client:
            response = client.get(
                self.endpoint,
                headers={"User-Agent": "Human-Agency-Engine-HORIZON/0.1"},
            )
            response.raise_for_status()
            return response.text

    def parse(self, payload: str | bytes, *, fetched_at: datetime | None = None) -> list[LiveEventCandidate]:
        fetched_at = fetched_at or datetime.utcnow()
        root = ET.fromstring(payload)
        entries = [node for node in root.iter() if _local_name(node.tag) == "entry"]
        result: list[LiveEventCandidate] = []
        for entry in entries:
            fields: dict[str, list[str]] = {}
            links: list[str] = []
            for node in entry.iter():
                name = _local_name(node.tag)
                text = (node.text or "").strip()
                if text:
                    fields.setdefault(name, []).append(text)
                if name == "link" and node.attrib.get("href"):
                    links.append(node.attrib["href"])

            def first(*names: str) -> str:
                for name in names:
                    values = fields.get(name.lower()) or []
                    if values:
                        return values[0]
                return ""

            external_key = first("identifier", "id") or sha256_dict(fields)[:32]
            title = first("title", "headline", "event") or "MeteoAlarm weather warning"
            summary = first("summary", "description", "content") or title
            observed_at = _parse_dt(first("updated", "published", "sent"), fallback=fetched_at)
            effective = first("effective", "onset")
            expires = first("expires")
            event_name = first("event")
            severity = first("severity")
            urgency = first("urgency")
            certainty = first("certainty")
            area = first("areadesc")
            geography = [_COUNTRY_ISO2.get(self.country_slug, self.country_slug.upper())]
            raw = {
                "provider": "MeteoAlarm",
                "canonical_event_id": external_key,
                "country_slug": self.country_slug,
                "event": event_name,
                "severity": severity,
                "urgency": urgency,
                "certainty": certainty,
                "area": area,
                "effective": effective,
                "expires": expires,
                "provider_fields": fields,
            }
            normalized_event = re.sub(r"[^a-z0-9]+", "_", event_name.lower()).strip("_") if event_name else "warning"
            result.append(
                LiveEventCandidate(
                    source_key=self.source_key,
                    external_key=_clean_external(external_key),
                    event_type=f"weather_alert_{normalized_event}"[:96],
                    title=title[:255],
                    summary=summary,
                    geography=geography,
                    source_url=links[0] if links else self.endpoint,
                    source_reliability=self.reliability,
                    occurred_at=observed_at,
                    observed_at=observed_at,
                    raw_facts=raw,
                )
            )
        return result


class HorizonLiveIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def _source_row(self, adapter) -> HorizonLiveSource:
        row = (
            self.db.query(HorizonLiveSource)
            .filter(HorizonLiveSource.source_key == adapter.source_key)
            .one_or_none()
        )
        if row is None:
            row = HorizonLiveSource(
                source_key=adapter.source_key,
                name=adapter.source_name,
                source_kind=adapter.source_kind,
                endpoint=adapter.endpoint,
                enabled=True,
                config={},
            )
            self.db.add(row)
            self.db.flush()
        else:
            row.name = adapter.source_name
            row.source_kind = adapter.source_kind
            row.endpoint = adapter.endpoint
        return row

    def ingest_candidates(self, adapter, candidates: list[LiveEventCandidate]) -> dict:
        source = self._source_row(adapter)
        created = 0
        duplicates = 0
        event_ids: list[int] = []
        for candidate in candidates:
            fingerprint_payload = {
                "external_key": candidate.external_key,
                "event_type": candidate.event_type,
                "title": candidate.title,
                "summary": candidate.summary,
                "geography": candidate.geography,
                "source_url": candidate.source_url,
                "occurred_at": candidate.occurred_at.isoformat(),
                "observed_at": candidate.observed_at.isoformat(),
                "raw_facts": candidate.raw_facts,
            }
            payload_hash = sha256_dict(fingerprint_payload)
            existing = (
                self.db.query(HorizonLiveIngestionRecord)
                .filter(
                    HorizonLiveIngestionRecord.source_key == candidate.source_key,
                    HorizonLiveIngestionRecord.external_key == candidate.external_key,
                    HorizonLiveIngestionRecord.payload_hash == payload_hash,
                )
                .one_or_none()
            )
            if existing:
                duplicates += 1
                event_ids.append(existing.event_id)
                continue

            external_hash = sha256_dict({"external_key": candidate.external_key})[:16]
            event_key = f"live:{candidate.source_key}:{external_hash}:{payload_hash[:16]}"[:160]
            event = HorizonGlobalEvent(
                event_key=event_key,
                event_type=candidate.event_type,
                title=candidate.title,
                summary=candidate.summary,
                geography=candidate.geography,
                source=candidate.source_key,
                source_url=candidate.source_url,
                source_reliability=candidate.source_reliability,
                raw_facts={
                    **candidate.raw_facts,
                    "live_source_key": candidate.source_key,
                    "external_key": candidate.external_key,
                    "payload_hash": payload_hash,
                },
                occurred_at=_utc_naive(candidate.occurred_at),
                first_observed_at=_utc_naive(candidate.observed_at),
                status="active",
            )
            self.db.add(event)
            self.db.flush()
            record = HorizonLiveIngestionRecord(
                source_key=candidate.source_key,
                external_key=candidate.external_key,
                payload_hash=payload_hash,
                event_id=event.id,
                provider_observed_at=_utc_naive(candidate.observed_at),
            )
            self.db.add(record)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                duplicates += 1
                continue
            created += 1
            event_ids.append(event.id)

        source.last_success_at = datetime.utcnow()
        source.last_error = ""
        self.db.commit()
        return {
            "source": adapter.source_key,
            "fetched": len(candidates),
            "created_snapshots": created,
            "duplicates": duplicates,
            "event_ids": event_ids,
        }

    def sync_adapter(self, adapter) -> dict:
        source = self._source_row(adapter)
        source.last_started_at = datetime.utcnow()
        self.db.commit()
        try:
            payload = adapter.fetch()
            candidates = adapter.parse(payload, fetched_at=datetime.utcnow())
            return self.ingest_candidates(adapter, candidates)
        except Exception as exc:
            source = self._source_row(adapter)
            source.last_error = str(exc)[:4000]
            self.db.commit()
            raise

    def adapters(self) -> list:
        result = [GDACSAdapter()]
        for country in settings.horizon_meteoalarm_country_list:
            result.append(MeteoAlarmAtomAdapter(country))
        return result

    def sync_all(self) -> dict:
        results: list[dict] = []
        for adapter in self.adapters():
            try:
                results.append(self.sync_adapter(adapter))
            except Exception as exc:
                results.append({"source": adapter.source_key, "error": str(exc)})
        return {
            "sources": results,
            "created_snapshots": sum(int(item.get("created_snapshots", 0)) for item in results),
            "errors": sum(1 for item in results if item.get("error")),
        }
