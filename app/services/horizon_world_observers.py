from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService


WHO_DON_ENDPOINT = "https://www.who.int/api/hubs/diseaseoutbreaknews"
NASA_EONET_ENDPOINT = "https://eonet.gsfc.nasa.gov/api/v3/events"


SOURCE_SPECS = {
    "who-disease-outbreak-news": HorizonSourceUpsert(
        source_key="who-disease-outbreak-news",
        name="WHO Disease Outbreak News",
        source_class="official_multilateral",
        adapter_kind="who_disease_outbreak_news_json",
        domains=["public_health", "epidemics", "humanitarian"],
        geography=["*"],
        base_locator=WHO_DON_ENDPOINT,
        trust_weight=0.96,
        refresh_seconds=1800,
        requires_credentials=False,
        metadata_json={
            "role": "official_outbreak_reporting",
            "publication_is_not_future_outcome": True,
        },
    ),
    "nasa-eonet": HorizonSourceUpsert(
        source_key="nasa-eonet",
        name="NASA Earth Observatory Natural Event Tracker",
        source_class="official_aggregator",
        adapter_kind="nasa_eonet_v3_json",
        domains=["natural_hazards", "earth_observation", "disaster"],
        geography=["*"],
        base_locator=NASA_EONET_ENDPOINT,
        trust_weight=0.88,
        refresh_seconds=900,
        requires_credentials=False,
        metadata_json={
            "role": "natural_event_discovery_aggregator",
            "aggregator_is_not_independent_confirmation": True,
        },
    ),
}


EONET_EVENT_TYPES = {
    "wildfires": "wildfire_emergency",
    "severeStorms": "severe_storm_emergency",
    "volcanoes": "volcanic_emergency",
    "floods": "flood_emergency",
    "drought": "drought_emergency",
    "landslides": "landslide_emergency",
    "seaLakeIce": "cryosphere_disruption",
    "dustHaze": "air_quality_hazard",
    "snow": "severe_winter_hazard",
    "tempExtremes": "temperature_extreme",
    "waterColor": "water_quality_anomaly",
}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: Any, limit: int = 2000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    return text[:limit]


class HorizonWorldObserverService:
    ENGINE_VERSION = "horizon-world-observers-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db
        self.sources = HorizonSourceService(db)

    def _source(self, key: str):
        return self.sources.upsert_source(SOURCE_SPECS[key])

    def _candidate(
        self,
        observation_id: int,
        *,
        event_type: str,
        title: str,
        geography: list[str],
        facts: dict[str, Any],
    ) -> int:
        row = self.sources.build_candidate(
            HorizonCandidateBuild(
                observation_ids=[observation_id],
                event_type=event_type,
                title=title[:255],
                geography=geography,
                normalized_facts=facts,
                normalizer_version=self.ENGINE_VERSION,
            )
        )
        return row.id

    @staticmethod
    def _safe(name: str, fn) -> dict[str, Any]:
        try:
            return {"name": name, "ok": True, "result": fn()}
        except Exception as exc:
            return {"name": name, "ok": False, "error": str(exc)[:500]}

    def poll(self) -> dict[str, Any]:
        with httpx.Client(
            timeout=httpx.Timeout(25.0),
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
        ) as client:
            rows = [
                self._safe("who_disease_outbreak_news", lambda: self.poll_who(client)),
                self._safe("nasa_eonet", lambda: self.poll_eonet(client)),
            ]
        return {
            "engine": self.ENGINE_VERSION,
            "sources": rows,
            "succeeded": sum(1 for row in rows if row.get("ok") is True),
            "failed": sum(1 for row in rows if row.get("ok") is False),
            "critical_semantics": {
                "official_report_is_current_evidence_not_future_outcome": True,
                "aggregator_event_is_not_independent_confirmation": True,
            },
        }

    def poll_who(self, client: httpx.Client) -> dict[str, Any]:
        source = self._source("who-disease-outbreak-news")
        response = client.get(
            WHO_DON_ENDPOINT,
            params={"$top": 30, "$orderby": "PublicationDate desc"},
        )
        response.raise_for_status()
        payload = response.json()
        rows: list[Any] = []
        if isinstance(payload, dict):
            for key in ("value", "Items", "items", "results"):
                candidate = payload.get(key)
                if isinstance(candidate, list):
                    rows = candidate
                    break
        elif isinstance(payload, list):
            rows = payload
        if not rows:
            raise ValueError("WHO Disease Outbreak News returned no items")

        cutoff = datetime.now(timezone.utc) - timedelta(days=21)
        created = 0
        candidate_ids: list[int] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            published = _parse_dt(item.get("PublicationDate") or item.get("PublicationDateAndTime"))
            if published is None or published < cutoff:
                continue
            title = _clean_text(item.get("Title") or item.get("OverrideTitle") or item.get("UrlName"), 255)
            if not title:
                continue
            source_id = str(item.get("Id") or item.get("SystemSourceKey") or item.get("UrlName") or title)
            country_hint = _clean_text(
                item.get("regionscountries") or item.get("TitleSuffix") or item.get("Summary"),
                500,
            )
            url = str(item.get("ItemDefaultUrl") or "").strip()
            if url.startswith("/"):
                url = "https://www.who.int" + url
            if not url:
                slug = str(item.get("UrlName") or "").strip()
                url = f"https://www.who.int/emergencies/disease-outbreak-news/item/{slug}" if slug else WHO_DON_ENDPOINT
            observation, is_new = self.sources.ingest_observation(
                source,
                HorizonObservationIngest(
                    external_key=f"who-don:{source_id}:{published.date().isoformat()}",
                    observation_type="official_disease_outbreak_report",
                    title=title,
                    summary=_clean_text(item.get("Summary") or item.get("Overview") or item.get("Assessment"), 2000),
                    source_url=url,
                    geography=[country_hint] if country_hint else ["GLOBAL"],
                    canonical_facts={
                        "publication_date": published.isoformat(),
                        "title_suffix": item.get("TitleSuffix"),
                        "don_id": item.get("DonId"),
                        "official_outbreak_report": True,
                    },
                    raw_metadata={
                        "provider": "World Health Organization",
                        "url_name": item.get("UrlName"),
                    },
                    event_time=published,
                    published_at=published,
                    observed_at=datetime.now(timezone.utc),
                ),
            )
            created += int(is_new)
            candidate_ids.append(
                self._candidate(
                    observation.id,
                    event_type="disease_outbreak_signal",
                    title=title,
                    geography=[country_hint] if country_hint else ["GLOBAL"],
                    facts={
                        "who_don": True,
                        "publication_date": published.isoformat(),
                        "current_outbreak_evidence": True,
                    },
                )
            )
        return {"new_observations": created, "candidate_ids": sorted(set(candidate_ids))}

    def poll_eonet(self, client: httpx.Client) -> dict[str, Any]:
        source = self._source("nasa-eonet")
        response = client.get(
            NASA_EONET_ENDPOINT,
            params={"status": "open", "days": 14, "limit": 100},
        )
        response.raise_for_status()
        payload = response.json()
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            raise ValueError("NASA EONET returned no event list")

        created = 0
        candidate_ids: list[int] = []
        category_counts: dict[str, int] = {}
        for item in events:
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("id") or "").strip()
            title = _clean_text(item.get("title"), 255)
            if not event_id or not title:
                continue
            categories = item.get("categories") if isinstance(item.get("categories"), list) else []
            category_ids = [str(row.get("id")) for row in categories if isinstance(row, dict) and row.get("id")]
            event_type = "natural_hazard_event"
            for category_id in category_ids:
                if category_id in EONET_EVENT_TYPES:
                    event_type = EONET_EVENT_TYPES[category_id]
                    break
            for category_id in category_ids:
                category_counts[category_id] = category_counts.get(category_id, 0) + 1

            geometry = item.get("geometry") if isinstance(item.get("geometry"), list) else []
            latest_geometry = geometry[-1] if geometry and isinstance(geometry[-1], dict) else {}
            event_at = _parse_dt(latest_geometry.get("date")) or _parse_dt(item.get("closed")) or datetime.now(timezone.utc)
            sources = item.get("sources") if isinstance(item.get("sources"), list) else []
            source_ids = [str(row.get("id")) for row in sources if isinstance(row, dict) and row.get("id")]
            links = [str(row.get("url")) for row in sources if isinstance(row, dict) and row.get("url")]
            observation, is_new = self.sources.ingest_observation(
                source,
                HorizonObservationIngest(
                    external_key=f"eonet:{event_id}:{event_at.isoformat()}",
                    observation_type="natural_event_discovery",
                    title=title,
                    summary=f"Événement naturel actif répertorié par NASA EONET ({', '.join(category_ids) or 'catégorie non précisée'}).",
                    source_url=str(item.get("link") or (links[0] if links else NASA_EONET_ENDPOINT)),
                    geography=["GLOBAL"],
                    canonical_facts={
                        "eonet_event_id": event_id,
                        "categories": category_ids,
                        "latest_geometry": latest_geometry,
                        "upstream_sources": source_ids,
                        "open_event": item.get("closed") is None,
                    },
                    raw_metadata={
                        "upstream_links": links[:10],
                        "aggregator": "NASA EONET",
                    },
                    event_time=event_at,
                    published_at=None,
                    observed_at=datetime.now(timezone.utc),
                ),
            )
            created += int(is_new)
            candidate_ids.append(
                self._candidate(
                    observation.id,
                    event_type=event_type,
                    title=title,
                    geography=["GLOBAL"],
                    facts={
                        "eonet_event_id": event_id,
                        "categories": category_ids,
                        "aggregated_discovery": True,
                    },
                )
            )
        return {
            "open_events_seen": len(events),
            "new_observations": created,
            "candidate_ids": sorted(set(candidate_ids)),
            "category_counts": category_counts,
        }
