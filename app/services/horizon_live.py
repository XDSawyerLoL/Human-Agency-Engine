from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import httpx
from sqlalchemy.orm import Session

from ..horizon_live_schemas import GDELT_QUERY_FAMILIES, HorizonGdeltPollRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest
from .horizon_sources import HorizonSourceService


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# Broad high-impact watch families. These are discovery queries, not truth rules.
GDELT_QUERY_PACK = {
    "supply": '(shortage OR shortages OR rationing OR "supply disruption" OR blockade OR "fuel shortage")',
    "weather_disaster": '(heatwave OR wildfire OR flooding OR earthquake OR cyclone OR hurricane OR drought)',
    "conflict_security": '("military strike" OR "missile attack" OR invasion OR sanctions OR coup OR "state of emergency")',
    "infrastructure": '(blackout OR outage OR "power cut" OR "internet outage" OR "transport strike" OR "rail strike")',
    "economy_labor": '(layoffs OR bankruptcy OR insolvency OR "factory closure" OR "mass layoffs")',
    "public_health": '("disease outbreak" OR epidemic OR pandemic OR "public health emergency")',
}


def _parse_seen_date(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _external_key(url: str) -> str:
    return f"gdelt-doc:{sha256(url.encode('utf-8')).hexdigest()[:48]}"


class HorizonLiveService:
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _gdelt_source(self) -> HorizonSource:
        HorizonSourceService(self.db).sync_builtin_sources()
        source = (
            self.db.query(HorizonSource)
            .filter(HorizonSource.source_key == "gdelt-doc-2")
            .one()
        )
        if not source.enabled:
            raise ValueError("GDELT source is disabled")
        if source.adapter_kind != "gdelt_doc_json":
            raise ValueError("GDELT source adapter kind is not approved for live polling")
        return source

    def poll_gdelt(
        self,
        request: HorizonGdeltPollRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        source = self._gdelt_source()
        families = request.families or sorted(GDELT_QUERY_FAMILIES)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=False,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        observed_at = datetime.now(timezone.utc)
        created_ids: list[int] = []
        replayed_ids: list[int] = []
        errors: list[dict] = []
        successful_families = 0

        try:
            for family in families:
                query = GDELT_QUERY_PACK[family]
                try:
                    response = client.get(
                        GDELT_DOC_ENDPOINT,
                        params={
                            "query": query,
                            "mode": "artlist",
                            "format": "json",
                            "sort": "datedesc",
                            "timespan": f"{request.timespan_minutes}min",
                            "maxrecords": request.max_records_per_query,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    articles = payload.get("articles", []) if isinstance(payload, dict) else []
                    if not isinstance(articles, list):
                        raise ValueError("GDELT JSON payload has no article list")
                    successful_families += 1
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"family": family, "error": str(exc)[:300]})
                    continue

                for article in articles:
                    if not isinstance(article, dict):
                        continue
                    url = str(article.get("url") or "").strip()
                    if not url.startswith(("http://", "https://")):
                        continue
                    external_key = _external_key(url)

                    # A live poll has a new observation timestamp every run, but an
                    # already-seen article is the same immutable raw observation.
                    # Resolve it before reconstructing the payload so recurring polls
                    # are idempotent without weakening the source ledger's collision rule.
                    existing = self.db.query(HorizonRawObservation).filter(
                        HorizonRawObservation.source_id == source.id,
                        HorizonRawObservation.external_key == external_key,
                    ).one_or_none()
                    if existing is not None:
                        replayed_ids.append(existing.id)
                        continue

                    title = str(article.get("title") or "").strip()[:255]
                    seen_at = _parse_seen_date(article.get("seendate"))
                    observation = HorizonObservationIngest(
                        external_key=external_key,
                        observation_type="news_report",
                        title=title,
                        summary="",
                        source_url=url,
                        # GDELT's sourcecountry describes the publisher, not necessarily
                        # where the reported event occurred. Do not mislabel it as event geography.
                        geography=[],
                        canonical_facts={
                            "watch_family": family,
                            "publisher_domain": article.get("domain"),
                            "publisher_country": article.get("sourcecountry"),
                            "language": article.get("language"),
                            "seen_date": article.get("seendate"),
                        },
                        raw_metadata={
                            "gdelt_query_family": family,
                            "social_image": article.get("socialimage"),
                            "url_mobile": article.get("url_mobile"),
                        },
                        event_time=None,
                        published_at=seen_at,
                        observed_at=observed_at,
                    )
                    row, created = HorizonSourceService(self.db).ingest_observation(source, observation)
                    if created:
                        created_ids.append(row.id)
                    else:
                        replayed_ids.append(row.id)
        finally:
            if owned_client:
                client.close()

        if successful_families == 0:
            raise RuntimeError("all GDELT live discovery queries failed")

        return {
            "source_key": source.source_key,
            "adapter": "gdelt_doc_json",
            "endpoint_allowlisted": GDELT_DOC_ENDPOINT,
            "families_requested": families,
            "families_succeeded": successful_families,
            "new_observations": len(created_ids),
            "replayed_observations": len(replayed_ids),
            "created_observation_ids": created_ids,
            "errors": errors,
            "promoted_events": 0,
            "candidates_created": 0,
            "detection_is_confirmation": False,
            "observed_at": observed_at.isoformat(),
        }
