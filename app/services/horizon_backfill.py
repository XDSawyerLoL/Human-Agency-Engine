from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalBackfillRun
from ..horizon_backfill_schemas import HorizonMeteoFranceArchiveBackfillRequest
from ..horizon_models import HorizonGlobalEvent
from ..horizon_source_models import HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_coverage import HorizonHistoricalCoverageService
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


METEOFRANCE_ARCHIVE_AVAILABLE_FROM = datetime(2022, 11, 28)
METEOFRANCE_ARCHIVE_TREE_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/45659157-1b03-4071-8fc2-b52e9a33a908"
)
METEOFRANCE_ARCHIVE_BASE_URL = "https://files.data.gouv.fr/meteofrance/data/vigilance/"
CARTE_MARKERS = ("QGFR40", "CDP_CARTE_EXTERNE")
TRANSMISSION_RE = re.compile(r"(20\d{12})")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _transmission_time(locator: str) -> datetime | None:
    match = TRANSMISSION_RE.search(locator)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _looks_like_carte_json(value: str) -> bool:
    upper = value.upper()
    return upper.endswith(".JSON") and any(marker in upper for marker in CARTE_MARKERS)


def _absolute_archive_url(value: str) -> str:
    value = value.strip()
    if value.startswith(("https://", "http://")):
        return value
    value = value.lstrip("/")
    for prefix in ("meteofrance/data/vigilance/", "data/vigilance/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return urljoin(METEOFRANCE_ARCHIVE_BASE_URL, value)


def discover_carte_urls(tree: object) -> list[str]:
    """Extract archived carte JSON locators from heterogeneous tree JSON shapes."""

    candidates: set[str] = set()

    def walk(node: object, inherited_path: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_path)
            return
        if isinstance(node, str):
            raw = node.strip()
            joined = f"{inherited_path.rstrip('/')}/{raw.lstrip('/')}" if inherited_path else raw
            if _looks_like_carte_json(raw):
                candidates.add(_absolute_archive_url(joined))
            elif _looks_like_carte_json(joined):
                candidates.add(_absolute_archive_url(joined))
            return
        if not isinstance(node, dict):
            return

        path_values = [
            str(node.get(key) or "").strip()
            for key in ("path", "prefix", "directory", "folder")
            if node.get(key)
        ]
        local_path = path_values[0] if path_values else inherited_path

        for key in ("url", "href", "download_url", "key", "object", "name", "filename", "path"):
            raw = node.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            text = raw.strip()
            joined = f"{local_path.rstrip('/')}/{text.lstrip('/')}" if local_path and text != local_path else text
            if _looks_like_carte_json(text):
                candidates.add(_absolute_archive_url(joined))
            elif _looks_like_carte_json(joined):
                candidates.add(_absolute_archive_url(joined))

        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, local_path)

    walk(tree)
    return sorted(candidates, key=lambda item: (_transmission_time(item) or datetime.min.replace(tzinfo=timezone.utc), item))


def extract_heat_intervals(payload: object, *, min_color_id: int, departments: set[str]) -> tuple[datetime, list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("Météo-France archive snapshot is not a JSON object")
    product = payload.get("product")
    if not isinstance(product, dict):
        raise ValueError("Météo-France archive snapshot has no product object")
    if str(product.get("warning_type") or "").lower() != "vigilance":
        raise ValueError("archive snapshot is not a Vigilance product")
    if str(product.get("type_cdp") or "").lower() not in {"cdp_carte_externe", "carte_externe"}:
        raise ValueError("archive snapshot is not a carte externe product")
    domain_id = str(product.get("domain_id") or "").upper()
    if domain_id and domain_id != "FRA":
        raise ValueError("archive snapshot does not cover metropolitan France")

    update_time = _parse_datetime(product.get("update_time"))
    if update_time is None:
        raise ValueError("archive snapshot has no valid product.update_time")

    intervals: list[dict] = []
    periods = product.get("periods")
    if not isinstance(periods, list):
        return update_time, intervals

    for period in periods:
        if not isinstance(period, dict):
            continue
        echeance = str(period.get("echeance") or "")
        period_start = _parse_datetime(period.get("begin_validity_time"))
        period_end = _parse_datetime(period.get("end_validity_time"))
        timelaps = period.get("timelaps") or {}
        domain_rows = timelaps.get("domain_ids", []) if isinstance(timelaps, dict) else []
        if not isinstance(domain_rows, list):
            continue
        for domain in domain_rows:
            if not isinstance(domain, dict):
                continue
            department = str(domain.get("domain_id") or "").upper().strip()
            if not department or department == "FRA" or department.startswith("ZDF_"):
                continue
            if departments and department not in departments:
                continue
            phenomena = domain.get("phenomenon_items") or []
            if not isinstance(phenomena, list):
                continue
            for phenomenon in phenomena:
                if not isinstance(phenomenon, dict) or str(phenomenon.get("phenomenon_id")) != "6":
                    continue
                try:
                    max_color = int(phenomenon.get("phenomenon_max_color_id") or 1)
                except (TypeError, ValueError):
                    max_color = 1
                timeline = phenomenon.get("timelaps_items") or []
                added_segment = False
                if isinstance(timeline, list):
                    for segment in timeline:
                        if not isinstance(segment, dict):
                            continue
                        try:
                            color = int(segment.get("color_id") or 1)
                        except (TypeError, ValueError):
                            continue
                        if color < min_color_id:
                            continue
                        begin = _parse_datetime(segment.get("begin_time")) or period_start
                        end = _parse_datetime(segment.get("end_time")) or period_end
                        if begin is None or end is None or end <= begin:
                            continue
                        intervals.append(
                            {
                                "department": department,
                                "echeance": echeance,
                                "begin": begin,
                                "end": end,
                                "color_id": color,
                                "phenomenon_max_color_id": max_color,
                            }
                        )
                        added_segment = True
                if not added_segment and max_color >= min_color_id and period_start and period_end and period_end > period_start:
                    intervals.append(
                        {
                            "department": department,
                            "echeance": echeance,
                            "begin": period_start,
                            "end": period_end,
                            "color_id": max_color,
                            "phenomenon_max_color_id": max_color,
                        }
                    )
    return update_time, intervals


class HorizonHistoricalBackfillService:
    ENGINE_VERSION = "horizon-historical-backfill-v0.1"
    ADAPTER_KIND = "meteofrance_vigilance_archive_json"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        payload = HorizonSourceUpsert(
            source_key="meteofrance-vigilance-archive",
            name="Météo-France Vigilance Archive",
            source_class="official_primary",
            adapter_kind=self.ADAPTER_KIND,
            domains=["weather", "civil_protection", "historical_archive"],
            geography=["FR"],
            base_locator=METEOFRANCE_ARCHIVE_TREE_URL,
            trust_weight=0.97,
            refresh_seconds=86400,
            requires_credentials=False,
            enabled=True,
            metadata_json={
                "role": "official_historical_weather_warning_archive",
                "available_from": "2022-11-28",
                "product_scope": "CDP_CARTE_EXTERNE/QGFR40",
                "historical_observed_at_rule": "product.update_time",
                "event_time_rule": "official_warning_publication_time",
                "direct_event_promotion": False,
            },
        )
        row = HorizonSourceService(self.db).upsert_source(payload)
        if not row.enabled:
            raise ValueError("Météo-France archive source is disabled")
        return row

    @staticmethod
    def _serialize_run(row: HorizonHistoricalBackfillRun, *, replayed: bool) -> dict:
        result = dict(row.result_snapshot or {})
        result.update(
            {
                "run_id": row.id,
                "run_key": row.run_key,
                "created_at": row.created_at.isoformat(),
                "replayed_existing_run": replayed,
            }
        )
        return result

    def _existing_episode_event(self, department: str, start: datetime, end: datetime, gap_hours: int) -> HorizonGlobalEvent | None:
        gap = timedelta(hours=gap_hours)
        rows = self.db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.event_type == "extreme_heat",
            HorizonGlobalEvent.source == "meteofrance-vigilance-archive",
            HorizonGlobalEvent.status == "active",
        ).all()
        for row in rows:
            geography = {str(item).upper() for item in (row.geography or [])}
            if department not in geography:
                continue
            normalized = (row.raw_facts or {}).get("normalized_facts") or {}
            raw_start = normalized.get("episode_start") if isinstance(normalized, dict) else None
            existing_start = _parse_datetime(raw_start) if raw_start else None
            anchor = _utc_naive(existing_start) if existing_start else row.occurred_at
            if start - gap <= anchor <= end + gap:
                return row
        return None

    @staticmethod
    def _merge_episodes(intervals: list[dict], gap_hours: int) -> list[dict]:
        gap = timedelta(hours=gap_hours)
        by_department: dict[str, list[dict]] = defaultdict(list)
        for item in intervals:
            by_department[item["department"]].append(item)
        episodes: list[dict] = []
        for department, rows in sorted(by_department.items()):
            rows.sort(key=lambda item: (item["begin"], item["end"], item["observation_id"]))
            current: dict | None = None
            for item in rows:
                if current is None or item["begin"] > current["end"] + gap:
                    if current is not None:
                        episodes.append(current)
                    current = {
                        "department": department,
                        "start": item["begin"],
                        "end": item["end"],
                        "max_color_id": item["color_id"],
                        "observation_ids": [item["observation_id"]],
                    }
                    continue
                current["end"] = max(current["end"], item["end"])
                current["max_color_id"] = max(current["max_color_id"], item["color_id"])
                if item["observation_id"] not in current["observation_ids"]:
                    current["observation_ids"].append(item["observation_id"])
            if current is not None:
                episodes.append(current)
        return episodes

    def backfill_meteofrance_vigilance(
        self,
        request: HorizonMeteoFranceArchiveBackfillRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        start_at = _utc_naive(request.start_at)
        end_at = _utc_naive(request.end_at)
        if start_at < METEOFRANCE_ARCHIVE_AVAILABLE_FROM:
            raise ValueError("Météo-France archived Vigilance is available from 2022-11-28")
        if end_at > datetime.utcnow() + timedelta(minutes=5):
            raise ValueError("historical backfill end_at cannot be in the future")
        if end_at - start_at > timedelta(days=366):
            raise ValueError("one historical backfill run is limited to 366 days; use consecutive batches")

        departments = {str(item).upper().strip() for item in request.departments if str(item).strip()}
        source = self._source()
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        try:
            tree_response = client.get(METEOFRANCE_ARCHIVE_TREE_URL)
            tree_response.raise_for_status()
            tree_payload = tree_response.json()
            discovered = discover_carte_urls(tree_payload)

            window_urls = []
            for url in discovered:
                transmitted = _transmission_time(url)
                if transmitted is None:
                    continue
                stamp = _utc_naive(transmitted)
                if start_at <= stamp <= end_at:
                    window_urls.append(url)
            window_urls.sort(key=lambda item: (_transmission_time(item), item))
            truncated = len(window_urls) > request.max_snapshots
            selected_urls = window_urls[: request.max_snapshots]
            discovery_fingerprint = sha256_dict({"selected_urls": selected_urls})
            run_key = sha256_dict(
                {
                    "engine": self.ENGINE_VERSION,
                    "adapter_kind": self.ADAPTER_KIND,
                    "source_id": source.id,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "departments": sorted(departments),
                    "min_color_id": request.min_color_id,
                    "max_snapshots": request.max_snapshots,
                    "merge_gap_hours": request.merge_gap_hours,
                    "discovery_fingerprint": discovery_fingerprint,
                }
            )
            existing = self.db.query(HorizonHistoricalBackfillRun).filter(
                HorizonHistoricalBackfillRun.run_key == run_key
            ).one_or_none()
            if existing is not None:
                return self._serialize_run(existing, replayed=True)

            source_service = HorizonSourceService(self.db)
            intervals: list[dict] = []
            created_observation_ids: list[int] = []
            replayed_observation_ids: list[int] = []
            errors: list[dict] = []
            snapshots_succeeded = 0

            for url in selected_urls:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                    update_time, heat_rows = extract_heat_intervals(
                        payload,
                        min_color_id=request.min_color_id,
                        departments=departments,
                    )
                    update_naive = _utc_naive(update_time)
                    if update_naive < start_at or update_naive > end_at:
                        continue
                    snapshots_succeeded += 1
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"url": url, "error": str(exc)[:300]})
                    continue

                meta = payload.get("meta") if isinstance(payload, dict) else {}
                snapshot_id = str((meta or {}).get("snapshot_id") or "") if isinstance(meta, dict) else ""
                for item in heat_rows:
                    digest = sha256(
                        (
                            f"{url}|{update_time.isoformat()}|{item['department']}|{item['echeance']}|"
                            f"{item['begin'].isoformat()}|{item['end'].isoformat()}|{item['color_id']}"
                        ).encode("utf-8")
                    ).hexdigest()[:56]
                    observation = HorizonObservationIngest(
                        external_key=f"mf-vigi-archive:{digest}",
                        observation_type="official_weather_warning_archive",
                        title=f"Vigilance canicule niveau {item['color_id']} — département {item['department']}",
                        summary="Archive officielle de la Vigilance Météo-France pour le phénomène canicule.",
                        source_url=url,
                        geography=["FR", item["department"]],
                        canonical_facts={
                            "phenomenon_id": "6",
                            "phenomenon": "canicule",
                            "color_id": item["color_id"],
                            "phenomenon_max_color_id": item["phenomenon_max_color_id"],
                            "department": item["department"],
                            "echeance": item["echeance"],
                            "begin_validity_time": item["begin"].isoformat(),
                            "end_validity_time": item["end"].isoformat(),
                            "product_update_time": update_time.isoformat(),
                        },
                        raw_metadata={
                            "engine": self.ENGINE_VERSION,
                            "adapter": self.ADAPTER_KIND,
                            "archive_tree": METEOFRANCE_ARCHIVE_TREE_URL,
                            "snapshot_id": snapshot_id,
                            "historical_timestamp_semantics": "observed_at_equals_official_product_update_time",
                            "event_semantics": "official_warning_publication_fact",
                        },
                        event_time=update_time,
                        published_at=update_time,
                        observed_at=update_time,
                    )
                    row, created = source_service.ingest_observation(source, observation)
                    if created:
                        created_observation_ids.append(row.id)
                    else:
                        replayed_observation_ids.append(row.id)
                    intervals.append({**item, "observation_id": row.id})

            episodes = self._merge_episodes(intervals, request.merge_gap_hours)
            promoted_event_ids: list[int] = []
            replayed_event_ids: list[int] = []
            candidate_ids: list[int] = []
            for episode in episodes:
                existing_event = self._existing_episode_event(
                    episode["department"],
                    _utc_naive(episode["start"]),
                    _utc_naive(episode["end"]),
                    request.merge_gap_hours,
                )
                if existing_event is not None:
                    replayed_event_ids.append(existing_event.id)
                    continue
                observation_ids = sorted(set(episode["observation_ids"]))[:100]
                candidate = source_service.build_candidate(
                    HorizonCandidateBuild(
                        observation_ids=observation_ids,
                        event_type="extreme_heat",
                        title=f"Vigilance canicule orange/rouge — département {episode['department']}",
                        geography=["FR", episode["department"]],
                        normalized_facts={
                            "archive": "meteofrance-vigilance",
                            "phenomenon_id": "6",
                            "department": episode["department"],
                            "episode_start": episode["start"].isoformat(),
                            "episode_end": episode["end"].isoformat(),
                            "max_color_id": episode["max_color_id"],
                            "historical_fact_only": True,
                            "trigger_fact_time": "official_product_update_time",
                        },
                        normalizer_version="horizon-mf-vigilance-archive-v0.1",
                    )
                )
                candidate_ids.append(candidate.id)
                event = source_service.promote_candidate(candidate)
                promoted_event_ids.append(event.id)

            coverage_complete = bool(selected_urls) and not truncated and not errors and snapshots_succeeded == len(selected_urls)
            coverage = HorizonHistoricalCoverageService(self.db).record_interval(
                source,
                coverage_kind="event",
                event_types=["extreme_heat"],
                signal_types=[],
                geography=["FR"] if not departments else ["FR", *sorted(departments)],
                start_at=start_at,
                end_at=end_at,
                completeness="complete" if coverage_complete else "partial",
                basis="provider_archive_tree_and_all_selected_carte_snapshots_fetched",
                provenance={
                    "engine": self.ENGINE_VERSION,
                    "archive_available_from": "2022-11-28",
                    "discovered_snapshots_in_window": len(window_urls),
                    "selected_snapshots": len(selected_urls),
                    "snapshots_succeeded": snapshots_succeeded,
                    "truncated": truncated,
                    "fetch_errors": len(errors),
                    "event_coverage_only": True,
                    "does_not_cover_behavioral_materialization_signals": True,
                },
            )

            result = {
                "engine": self.ENGINE_VERSION,
                "adapter": self.ADAPTER_KIND,
                "source_key": source.source_key,
                "window": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
                "archive_tree_url": METEOFRANCE_ARCHIVE_TREE_URL,
                "archive_available_from": "2022-11-28",
                "discovered_carte_snapshots": len(discovered),
                "snapshots_in_window": len(window_urls),
                "snapshots_selected": len(selected_urls),
                "snapshots_succeeded": snapshots_succeeded,
                "truncated_by_max_snapshots": truncated,
                "observations_created": len(created_observation_ids),
                "observations_replayed": len(replayed_observation_ids),
                "candidate_ids": candidate_ids,
                "events_promoted": len(promoted_event_ids),
                "promoted_event_ids": promoted_event_ids,
                "events_replayed": len(set(replayed_event_ids)),
                "replayed_event_ids": sorted(set(replayed_event_ids)),
                "episodes_detected": len(episodes),
                "errors": errors,
                "event_coverage_interval_id": coverage.id,
                "event_coverage_complete": coverage.completeness == "complete",
                "critical_semantics": {
                    "historical_observed_at_uses_provider_update_time": True,
                    "historical_event_time_uses_provider_update_time": True,
                    "warning_validity_start_is_not_treated_as_already_occurred": True,
                    "adapter_directly_creates_confirmed_event": False,
                    "promotion_uses_source_intelligence": True,
                    "archive_event_coverage_is_materialization_signal_coverage": False,
                    "absence_of_behavioral_signal_means_non_occurrence": False,
                    "numeric_probabilities_enabled": False,
                },
            }
            run = HorizonHistoricalBackfillRun(
                run_key=run_key,
                engine_version=self.ENGINE_VERSION,
                adapter_kind=self.ADAPTER_KIND,
                source_id=source.id,
                requested_start_at=start_at,
                requested_end_at=end_at,
                request_snapshot=request.model_dump(mode="json"),
                result_snapshot=result,
                status="completed_with_errors" if errors else "completed",
            )
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return self._serialize_run(run, replayed=False)
        finally:
            if owned_client:
                client.close()

    def list_runs(self, *, limit: int = 100) -> list[dict]:
        rows = (
            self.db.query(HorizonHistoricalBackfillRun)
            .order_by(HorizonHistoricalBackfillRun.created_at.desc(), HorizonHistoricalBackfillRun.id.desc())
            .limit(limit)
            .all()
        )
        return [self._serialize_run(row, replayed=False) for row in rows]
