from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import re
import unicodedata
from urllib.parse import unquote, urlparse
from zipfile import BadZipFile, ZipFile

import httpx
from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalBackfillRun
from ..horizon_models import HorizonGlobalEvent
from ..horizon_supply_trigger_schemas import HorizonGdeltFuelSupplyTriggerBackfillRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest
from .horizon_coverage import HorizonHistoricalCoverageService
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


GDELT_EVENTS_BASE_URL = "https://data.gdeltproject.org/events"
ALLOWED_DOWNLOAD_HOSTS = {"data.gdeltproject.org"}
MAX_DAILY_ZIP_BYTES = 16 * 1024 * 1024
MAX_DAILY_CSV_BYTES = 256 * 1024 * 1024
MAX_TOTAL_ZIP_BYTES = 256 * 1024 * 1024

SOURCE_KEY = "gdelt1-fuel-supply-trigger-replay"
SOURCE_SPEC = {
    "name": "GDELT 1.0 daily fuel-supply disruption report precursor",
    "source_class": "news_global",
    "adapter_kind": "gdelt1_daily_event_fuel_supply_precursor_v1",
    "domains": ["supply", "fuel", "media_attention", "historical_archive"],
    "geography": ["FR"],
    "base_locator": GDELT_EVENTS_BASE_URL,
    "trust_weight": 0.55,
    "refresh_seconds": 86400,
    "requires_credentials": False,
    "metadata_json": {
        "role": "historical_media_precursor_not_ground_truth",
        "sourceurl_required_from": "2013-04-01",
        "cameo_event_prefixes": ["143", "144"],
        "cameo_semantics": {
            "143": "conduct strike or boycott",
            "144": "obstruct passage or block",
        },
        "event_geography_required": "ActionGeo_CountryCode=FR",
        "root_event_required": True,
        "fuel_relevance_is_high_precision_metadata_filter": True,
        "media_report_cluster_is_real_world_disruption_confirmation": False,
    },
}

# Fixed v1 filter. Keeping this in code rather than in the request prevents an
# operator from tuning keywords after inspecting outcome labels.
FUEL_RELEVANCE_TERMS = (
    "carburant",
    "carburants",
    "diesel",
    "essence",
    "esso",
    "exxon",
    "exxonmobil",
    "fuel",
    "gasoil",
    "gasoline",
    "gazole",
    "oil depot",
    "oil terminal",
    "petrol",
    "petroleum",
    "raffinerie",
    "raffineries",
    "refinery",
    "refineries",
    "totalenergies",
)

# GDELT 1.0 daily stream, April 2013+.
IDX_GLOBAL_EVENT_ID = 0
IDX_SQLDATE = 1
IDX_ACTOR1_NAME = 6
IDX_ACTOR2_NAME = 16
IDX_IS_ROOT_EVENT = 25
IDX_EVENT_CODE = 26
IDX_EVENT_BASE_CODE = 27
IDX_NUM_MENTIONS = 31
IDX_NUM_SOURCES = 32
IDX_NUM_ARTICLES = 33
IDX_ACTION_GEO_FULLNAME = 50
IDX_ACTION_GEO_COUNTRY = 51
IDX_ACTION_GEO_ADM1 = 52
IDX_DATE_ADDED = 56
IDX_SOURCE_URL = 57
MIN_COLUMNS = 58


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _iter_days(start_at: datetime, end_at: datetime) -> list[date]:
    start_day = _utc_naive(start_at).date()
    end_day = _utc_naive(end_at).date()
    values = []
    current = start_day
    while current <= end_day:
        values.append(current)
        current += timedelta(days=1)
    return values


def _daily_url(day: date) -> str:
    return f"{GDELT_EVENTS_BASE_URL}/{day:%Y%m%d}.export.CSV.zip"


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return default


def _parse_sql_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_date_added(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _fold_text(value: str) -> str:
    value = unquote(str(value or "")).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _fuel_relevance(row: list[str]) -> tuple[bool, list[str]]:
    source_url = row[IDX_SOURCE_URL]
    actor1 = row[IDX_ACTOR1_NAME]
    actor2 = row[IDX_ACTOR2_NAME]
    # Actor names are part of the contemporaneous coded event metadata. We do
    # not fetch article bodies or reconstruct future summaries.
    searchable = _fold_text(" ".join([source_url, actor1, actor2]))
    matched = sorted({term for term in FUEL_RELEVANCE_TERMS if _fold_text(term) in searchable})
    return bool(matched), matched


def _source_domain(url: str) -> str:
    try:
        host = (urlparse(str(url)).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _parse_daily_zip(content: bytes, *, day: date, max_events: int) -> dict:
    if len(content) > MAX_DAILY_ZIP_BYTES:
        raise ValueError("GDELT daily ZIP exceeds configured compressed-size limit")
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = [
                item for item in archive.infolist()
                if item.filename.lower().endswith((".csv", ".tsv"))
            ]
            if len(members) != 1:
                raise ValueError("GDELT daily ZIP must contain exactly one event CSV")
            member = members[0]
            if member.file_size > MAX_DAILY_CSV_BYTES:
                raise ValueError("GDELT daily CSV exceeds configured uncompressed-size limit")

            matches: list[dict] = []
            rows_seen = 0
            with archive.open(member) as raw:
                stream = TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                reader = csv.reader(stream, delimiter="\t")
                for row in reader:
                    rows_seen += 1
                    if len(row) < MIN_COLUMNS:
                        continue
                    if row[IDX_ACTION_GEO_COUNTRY].strip().upper() != "FR":
                        continue
                    if row[IDX_IS_ROOT_EVENT].strip() != "1":
                        continue

                    event_code = row[IDX_EVENT_CODE].strip()
                    event_base_code = row[IDX_EVENT_BASE_CODE].strip()
                    if not (
                        event_code.startswith(("143", "144"))
                        or event_base_code.startswith(("143", "144"))
                    ):
                        continue

                    relevant, matched_terms = _fuel_relevance(row)
                    if not relevant:
                        continue

                    source_url = row[IDX_SOURCE_URL].strip()
                    if not source_url.startswith(("http://", "https://")):
                        continue
                    first_seen = _parse_date_added(row[IDX_DATE_ADDED])
                    event_day = _parse_sql_date(row[IDX_SQLDATE])
                    if first_seen is None or event_day is None:
                        continue

                    matches.append({
                        "global_event_id": row[IDX_GLOBAL_EVENT_ID].strip(),
                        "sql_date": row[IDX_SQLDATE].strip(),
                        "event_code": event_code,
                        "event_base_code": event_base_code,
                        "actor1_name": row[IDX_ACTOR1_NAME].strip(),
                        "actor2_name": row[IDX_ACTOR2_NAME].strip(),
                        "action_geo_fullname": row[IDX_ACTION_GEO_FULLNAME].strip(),
                        "action_geo_adm1": row[IDX_ACTION_GEO_ADM1].strip(),
                        "num_mentions": _parse_int(row[IDX_NUM_MENTIONS]),
                        "num_sources": _parse_int(row[IDX_NUM_SOURCES]),
                        "num_articles": _parse_int(row[IDX_NUM_ARTICLES]),
                        "source_url": source_url,
                        "source_domain": _source_domain(source_url),
                        "matched_relevance_terms": matched_terms,
                        "event_time": event_day.isoformat(),
                        "first_seen": first_seen.isoformat(),
                    })
                    if len(matches) >= max_events:
                        break
    except BadZipFile as exc:
        raise ValueError("GDELT daily event file is not a valid ZIP archive") from exc

    return {
        "day": day.isoformat(),
        "rows_seen": rows_seen,
        "matches": matches,
        "truncated_by_max_events": len(matches) >= max_events,
    }


class HorizonGdeltFuelSupplyTriggerBackfillService:
    ENGINE_VERSION = "horizon-gdelt1-fuel-supply-trigger-v0.1"
    ADAPTER_KIND = SOURCE_SPEC["adapter_kind"]
    EVENT_TYPE = "fuel_supply_disruption_report_cluster"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        row = self.db.query(HorizonSource).filter(
            HorizonSource.source_key == SOURCE_KEY
        ).one_or_none()
        if row is None:
            row = HorizonSource(source_key=SOURCE_KEY, enabled=True, **SOURCE_SPEC)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        else:
            for key in ("source_class", "adapter_kind", "base_locator"):
                if getattr(row, key) != SOURCE_SPEC[key]:
                    raise ValueError(
                        f"GDELT fuel trigger source {key} differs from approved adapter contract"
                    )
        if not row.enabled:
            raise ValueError("GDELT fuel trigger replay source is disabled")
        return row

    @staticmethod
    def _serialize_run(row: HorizonHistoricalBackfillRun, *, replayed: bool) -> dict:
        result = dict(row.result_snapshot or {})
        result.update({
            "run_id": row.id,
            "run_key": row.run_key,
            "created_at": row.created_at.isoformat(),
            "replayed_existing_run": replayed,
        })
        return result

    def backfill(
        self,
        request: HorizonGdeltFuelSupplyTriggerBackfillRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        days = _iter_days(request.start_at, request.end_at)
        if len(days) > request.max_days:
            raise ValueError("requested GDELT trigger window exceeds max_days")

        source = self._source()
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/zip"},
            )

        downloaded: list[dict] = []
        total_bytes = 0
        failures: list[dict] = []
        try:
            for day in days:
                url = _daily_url(day)
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    if response.url.host not in ALLOWED_DOWNLOAD_HOSTS:
                        raise RuntimeError("GDELT daily file redirected outside the approved host")
                    content = response.content
                    total_bytes += len(content)
                    if total_bytes > MAX_TOTAL_ZIP_BYTES:
                        raise ValueError(
                            "GDELT trigger request exceeds configured total download-size limit"
                        )
                    parsed = _parse_daily_zip(
                        content,
                        day=day,
                        max_events=request.max_events_per_day,
                    )
                    downloaded.append({
                        "day": day.isoformat(),
                        "url": url,
                        "sha256": sha256(content).hexdigest(),
                        "bytes": len(content),
                        "parsed": parsed,
                    })
                except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                    failures.append({
                        "day": day.isoformat(),
                        "url": url,
                        "error": str(exc)[:500],
                    })
        finally:
            if owned_client:
                client.close()

        content_fingerprint = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "request": request.model_dump(mode="json"),
            "files": [
                {"day": item["day"], "sha256": item["sha256"]}
                for item in downloaded
            ],
            "failures": failures,
        })
        run_key = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "adapter_kind": self.ADAPTER_KIND,
            "source_id": source.id,
            "content_fingerprint": content_fingerprint,
            "request": request.model_dump(mode="json"),
        })
        existing = self.db.query(HorizonHistoricalBackfillRun).filter(
            HorizonHistoricalBackfillRun.run_key == run_key
        ).one_or_none()
        if existing is not None:
            return self._serialize_run(existing, replayed=True)

        source_service = HorizonSourceService(self.db)
        raw_created = 0
        raw_replayed = 0
        clusters_created = 0
        clusters_replayed = 0
        cluster_rows: list[dict] = []
        any_truncated = False

        for item in downloaded:
            parsed = item["parsed"]
            any_truncated = any_truncated or bool(parsed["truncated_by_max_events"])
            matches = parsed["matches"]
            observation_ids: list[int] = []
            for match in matches:
                external_key = f"gdelt1:{match['global_event_id']}"
                observation = HorizonObservationIngest(
                    external_key=external_key,
                    observation_type="media_coded_fuel_supply_disruption_report",
                    title=(
                        f"GDELT report precursor {match['event_code']} — "
                        f"{match['action_geo_fullname'] or 'France'}"
                    ),
                    summary="",
                    source_url=match["source_url"],
                    geography=["FR"],
                    canonical_facts={
                        "global_event_id": match["global_event_id"],
                        "cameo_event_code": match["event_code"],
                        "cameo_event_base_code": match["event_base_code"],
                        "actor1_name": match["actor1_name"],
                        "actor2_name": match["actor2_name"],
                        "action_geo_fullname": match["action_geo_fullname"],
                        "action_geo_adm1": match["action_geo_adm1"],
                        "matched_relevance_terms": match["matched_relevance_terms"],
                        "num_mentions": match["num_mentions"],
                        "num_sources": match["num_sources"],
                        "num_articles": match["num_articles"],
                        "source_domain": match["source_domain"],
                        "underlying_disruption_confirmed": False,
                        "fact_asserted": "a GDELT-coded contemporaneous report matched the fixed fuel-supply disruption filter",
                    },
                    raw_metadata={
                        "engine": self.ENGINE_VERSION,
                        "adapter": self.ADAPTER_KIND,
                        "daily_file_sha256": item["sha256"],
                        "daily_file_url": item["url"],
                        "filter_version": "fuel-url-actor-terms-v1",
                        "cameo_prefixes": ["143", "144"],
                        "article_body_fetched": False,
                        "source_count_is_truth_vote": False,
                    },
                    event_time=datetime.fromisoformat(match["event_time"]),
                    published_at=datetime.fromisoformat(match["first_seen"]),
                    observed_at=datetime.fromisoformat(match["first_seen"]),
                )
                row, created = source_service.ingest_observation(source, observation)
                observation_ids.append(row.id)
                if created:
                    raw_created += 1
                else:
                    raw_replayed += 1

            if not matches:
                continue
            domains = sorted({
                match["source_domain"]
                for match in matches
                if match["source_domain"]
            })
            if len(domains) < request.min_distinct_domains_per_day:
                continue

            day = date.fromisoformat(item["day"])
            day_start, _ = _day_bounds(day)
            first_seen = min(
                datetime.fromisoformat(match["first_seen"])
                for match in matches
            )
            event_key = "gdelt1-fuel-report-cluster:" + sha256_dict({
                "engine": self.ENGINE_VERSION,
                "day": item["day"],
                "daily_sha256": item["sha256"],
                "observation_ids": sorted(observation_ids),
                "min_distinct_domains": request.min_distinct_domains_per_day,
            })[:48]
            event = self.db.query(HorizonGlobalEvent).filter(
                HorizonGlobalEvent.event_key == event_key
            ).one_or_none()
            created = False
            if event is None:
                event = HorizonGlobalEvent(
                    event_key=event_key,
                    event_type=self.EVENT_TYPE,
                    title=f"France — cluster de signalements grève/blocage liés au carburant — {item['day']}",
                    summary=(
                        "Cluster quotidien de rapports médiatiques codés par GDELT comme grève/boycott "
                        "ou blocage, filtrés par métadonnées liées au carburant. "
                        "Ce cluster ne confirme pas à lui seul une perturbation réelle d'approvisionnement."
                    ),
                    geography=["FR"],
                    source=SOURCE_KEY,
                    source_url=item["url"],
                    source_reliability=0.55,
                    raw_facts={
                        "engine": self.ENGINE_VERSION,
                        "cluster_kind": "media_report_cluster",
                        "observation_ids": sorted(observation_ids),
                        "matching_gdelt_events": len(matches),
                        "distinct_source_domains": domains,
                        "distinct_source_domain_count": len(domains),
                        "min_distinct_domains_threshold": request.min_distinct_domains_per_day,
                        "cameo_event_prefixes": ["143", "144"],
                        "filter_terms_version": "fuel-url-actor-terms-v1",
                        "underlying_disruption_confirmed": False,
                        "cluster_threshold_is_truth_vote": False,
                        "historical_point_in_time_basis": "earliest GDELT DATEADDED among matched reports",
                    },
                    occurred_at=day_start,
                    first_observed_at=first_seen,
                    status="active",
                )
                self.db.add(event)
                self.db.commit()
                self.db.refresh(event)
                clusters_created += 1
                created = True
            else:
                clusters_replayed += 1

            cluster_rows.append({
                "event_id": event.id,
                "event_key": event.event_key,
                "day": item["day"],
                "first_observed_at": event.first_observed_at.isoformat(),
                "matching_gdelt_events": len(matches),
                "distinct_source_domains": domains,
                "created": created,
            })

        start_naive = _utc_naive(request.start_at)
        end_naive = _utc_naive(request.end_at)
        coverage_complete = (
            len(downloaded) == len(days)
            and not failures
            and not any_truncated
        )
        coverage = HorizonHistoricalCoverageService(self.db).record_interval(
            source,
            coverage_kind="event",
            event_types=[self.EVENT_TYPE],
            signal_types=[],
            geography=["FR"],
            start_at=start_naive,
            end_at=end_naive,
            completeness="complete" if coverage_complete else "partial",
            basis="gdelt1_daily_event_files_fixed_cameo_and_fuel_metadata_filter",
            provenance={
                "engine": self.ENGINE_VERSION,
                "requested_days": len(days),
                "downloaded_days": len(downloaded),
                "failed_days": failures,
                "any_day_truncated": any_truncated,
                "cameo_event_prefixes": ["143", "144"],
                "filter_terms": list(FUEL_RELEVANCE_TERMS),
                "root_event_required": True,
                "action_country_required": "FR",
                "sourceurl_required": True,
                "coverage_complete_means": "the configured GDELT source/filter was fully replayed for the window",
                "coverage_complete_does_not_mean": "all real-world fuel disruptions were reported or correctly coded by GDELT",
            },
        )

        result = {
            "engine": self.ENGINE_VERSION,
            "adapter": self.ADAPTER_KIND,
            "source_key": source.source_key,
            "window": {
                "start_at": start_naive.isoformat(),
                "end_at": end_naive.isoformat(),
            },
            "days_requested": len(days),
            "days_downloaded": len(downloaded),
            "download_failures": failures,
            "compressed_bytes_downloaded": total_bytes,
            "raw_observations_created": raw_created,
            "raw_observations_replayed": raw_replayed,
            "report_clusters_created": clusters_created,
            "report_clusters_replayed": clusters_replayed,
            "clusters": cluster_rows,
            "event_coverage_interval_id": coverage.id,
            "event_coverage_complete": coverage.completeness == "complete",
            "critical_semantics": {
                "trigger_is_media_precursor": True,
                "trigger_is_underlying_disruption_confirmation": False,
                "source_count_is_truth_vote": False,
                "cluster_threshold_is_probability": False,
                "historical_timestamp_uses_contemporaneous_dateadded": True,
                "article_body_fetched_or_reconstructed": False,
                "provider_failure_is_negative_evidence": False,
                "numeric_probabilities_enabled": False,
            },
        }

        run = HorizonHistoricalBackfillRun(
            run_key=run_key,
            engine_version=self.ENGINE_VERSION,
            adapter_kind=self.ADAPTER_KIND,
            source_id=source.id,
            requested_start_at=start_naive,
            requested_end_at=end_naive,
            request_snapshot=request.model_dump(mode="json"),
            result_snapshot=result,
            status="completed" if coverage_complete else "completed_partial",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return self._serialize_run(run, replayed=False)
