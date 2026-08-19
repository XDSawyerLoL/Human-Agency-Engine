from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from ..horizon_global_alert_schemas import HorizonMeteoAlarmPollRequest, METEOALARM_COUNTRY_TO_ISO2
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


METEOALARM_ATOM_TEMPLATE = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{country}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first(fields: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = fields.get(name.lower()) or []
        if values:
            return values[0]
    return ""


def _entry_data(entry: ET.Element) -> dict:
    fields: dict[str, list[str]] = {}
    links: list[dict] = []
    attributes: list[dict] = []
    for node in entry.iter():
        name = _local_name(node.tag)
        text = (node.text or "").strip()
        if text:
            fields.setdefault(name, []).append(text)
        if node.attrib:
            attributes.append({"tag": name, "attributes": dict(sorted(node.attrib.items()))})
        if name == "link" and node.attrib.get("href"):
            links.append({
                "href": node.attrib.get("href"),
                "rel": node.attrib.get("rel"),
                "type": node.attrib.get("type"),
                "title": node.attrib.get("title"),
            })
    raw_xml = ET.tostring(entry, encoding="utf-8")
    identifier = _first(fields, "identifier", "id")
    updated_text = _first(fields, "updated", "published", "sent")
    effective_text = _first(fields, "effective", "onset")
    return {
        "fields": fields,
        "links": links,
        "attributes": attributes,
        "identifier": identifier,
        "updated_at": _parse_datetime(updated_text),
        "effective_at": _parse_datetime(effective_text),
        "entry_fingerprint": sha256(raw_xml).hexdigest(),
    }


class HorizonMeteoAlarmService:
    ENGINE_VERSION = "horizon-meteoalarm-atom-source-intelligence-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self, country: str) -> HorizonSource:
        iso2 = METEOALARM_COUNTRY_TO_ISO2[country]
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key=f"meteoalarm:{country}",
                name=f"MeteoAlarm Atom — {country}",
                source_class="official_aggregator",
                adapter_kind="meteoalarm_atom_warning_feed",
                domains=["weather", "civil_protection", "european_warnings", "realtime"],
                geography=[iso2],
                base_locator=METEOALARM_ATOM_TEMPLATE.format(country=country),
                trust_weight=0.93,
                refresh_seconds=600,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "official_warning_aggregator_not_independent_national_origin",
                    "evidence_roles": ["confirmation", "physical_state"],
                    "independence_family": f"weather-warning:{country}",
                    "provider": "MeteoAlarm / EUMETNET members",
                    "format": "Atom",
                    "country_slug": country,
                    "country_iso2": iso2,
                    "direct_edr_api_requires_token": True,
                    "adapter_direct_event_promotion": False,
                },
            )
        )
        if not source.enabled:
            raise ValueError(f"MeteoAlarm source is disabled for {country}")
        return source

    @staticmethod
    def parse_atom(payload: str | bytes) -> list[dict]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError("MeteoAlarm response is not valid Atom XML") from exc
        entries = [node for node in root.iter() if _local_name(node.tag) == "entry"]
        parsed: list[dict] = []
        for entry in entries:
            data = _entry_data(entry)
            fields = data["fields"]
            title = _first(fields, "title", "headline", "event") or "MeteoAlarm weather warning"
            summary = _first(fields, "summary", "description", "content") or title
            event = _first(fields, "event")
            severity = _first(fields, "severity")
            urgency = _first(fields, "urgency")
            certainty = _first(fields, "certainty")
            area = _first(fields, "areadesc")
            expires = _parse_datetime(_first(fields, "expires"))
            identifier = data["identifier"] or data["entry_fingerprint"][:32]
            parsed.append({
                "identifier": identifier,
                "title": title[:255],
                "summary": summary,
                "event": event,
                "severity": severity,
                "urgency": urgency,
                "certainty": certainty,
                "area": area,
                "updated_at": data["updated_at"],
                "effective_at": data["effective_at"],
                "expires_at": expires,
                "fields": fields,
                "links": data["links"],
                "attributes": data["attributes"],
                "entry_fingerprint": data["entry_fingerprint"],
            })
        return parsed

    def _poll_country(
        self,
        country: str,
        request: HorizonMeteoAlarmPollRequest,
        *,
        client: httpx.Client,
        observed_at: datetime,
    ) -> dict:
        source = self._source(country)
        endpoint = METEOALARM_ATOM_TEMPLATE.format(country=country)
        response = client.get(endpoint)
        response.raise_for_status()
        entries = self.parse_atom(response.content)[: request.max_entries_per_country]
        iso2 = METEOALARM_COUNTRY_TO_ISO2[country]
        service = HorizonSourceService(self.db)
        created_ids: list[int] = []
        replayed_ids: list[int] = []
        for item in entries:
            identifier_hash = sha256(str(item["identifier"]).encode("utf-8")).hexdigest()[:16]
            external_key = (
                f"meteoalarm:{country}:{identifier_hash}:{item['entry_fingerprint'][:24]}"
            )[:192]
            existing = self.db.query(HorizonRawObservation).filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.external_key == external_key,
            ).one_or_none()
            if existing is not None:
                replayed_ids.append(existing.id)
                continue
            source_url = endpoint
            for link in item["links"]:
                href = str(link.get("href") or "").strip()
                if href:
                    source_url = href
                    break
            observation = HorizonObservationIngest(
                external_key=external_key,
                observation_type="official_weather_warning_aggregated_snapshot",
                title=item["title"],
                summary=item["summary"],
                source_url=source_url,
                geography=[iso2],
                canonical_facts={
                    "provider": "MeteoAlarm",
                    "country_slug": country,
                    "country_iso2": iso2,
                    "canonical_warning_id": item["identifier"],
                    "event": item["event"],
                    "severity": item["severity"],
                    "urgency": item["urgency"],
                    "certainty": item["certainty"],
                    "area": item["area"],
                    "provider_updated_at": item["updated_at"].isoformat() if item["updated_at"] else None,
                    "effective_at": item["effective_at"].isoformat() if item["effective_at"] else None,
                    "expires_at": item["expires_at"].isoformat() if item["expires_at"] else None,
                },
                raw_metadata={
                    "engine": self.ENGINE_VERSION,
                    "provider_fields": item["fields"],
                    "provider_links": item["links"],
                    "provider_attributes": item["attributes"],
                    "entry_fingerprint": item["entry_fingerprint"],
                    "atom_feed": endpoint,
                    "adapter_direct_event_promotion": False,
                },
                event_time=item["effective_at"] or item["updated_at"],
                published_at=item["updated_at"],
                observed_at=observed_at,
            )
            row, _ = service.ingest_observation(source, observation)
            created_ids.append(row.id)
        return {
            "country": country,
            "iso2": iso2,
            "source_key": source.source_key,
            "entries_received": len(entries),
            "new_observations": len(set(created_ids)),
            "replayed_observations": len(set(replayed_ids)),
            "observation_ids": sorted(set(created_ids + replayed_ids)),
        }

    def poll(
        self,
        request: HorizonMeteoAlarmPollRequest,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        fetched_at = observed_at or datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/atom+xml,application/xml,text/xml"},
            )
        results: list[dict] = []
        errors: list[dict] = []
        try:
            for country in request.countries:
                try:
                    results.append(
                        self._poll_country(country, request, client=client, observed_at=fetched_at)
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"country": country, "error": str(exc)[:300]})
        finally:
            if owned_client:
                client.close()
        return {
            "engine": self.ENGINE_VERSION,
            "countries_requested": request.countries,
            "countries_succeeded": len(results),
            "countries_failed": len(errors),
            "new_observations": sum(int(item["new_observations"]) for item in results),
            "replayed_observations": sum(int(item["replayed_observations"]) for item in results),
            "observation_ids": sorted({
                observation_id
                for item in results
                for observation_id in item["observation_ids"]
            }),
            "countries": results,
            "errors": errors,
            "critical_semantics": {
                "adapter_creates_confirmed_event": False,
                "source_class": "official_aggregator",
                "national_origin_may_overlap_direct_national_source": True,
                "independence_family_prevents_double_counting": True,
                "provider_timestamp_preserved": True,
                "fetch_time_separate_from_provider_time": True,
                "severity_is_probability": False,
            },
        }
