from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

import httpx
from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalBackfillRun
from ..horizon_fuel_schemas import HorizonFuelHistoricalBackfillRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest
from .horizon_coverage import HorizonHistoricalCoverageService
from .horizon_fuel import FUEL_NAMES, _department_from_postal, _parse_feed_datetime
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


ANNUAL_ARCHIVE_BASE_URL = "https://donnees.roulez-eco.fr/opendata/annee"
ANNUAL_ARCHIVE_AVAILABLE_FROM = 2007
ALLOWED_DOWNLOAD_HOSTS = {"donnees.roulez-eco.fr"}
MAX_ZIP_BYTES = 96 * 1024 * 1024
MAX_XML_BYTES = 768 * 1024 * 1024

SOURCE_KEY = "fr-fuel-ruptures-annual-archive"
SOURCE_SPEC = {
    "name": "Prix Carburants — archives annuelles des ruptures",
    "source_class": "official_statistical",
    "adapter_kind": "fr_fuel_annual_ruptures_zip_xml_v1",
    "domains": ["fuel", "supply", "historical_archive", "behavioral_outcomes"],
    "geography": ["FR"],
    "base_locator": ANNUAL_ARCHIVE_BASE_URL,
    "trust_weight": 0.96,
    "refresh_seconds": 86400,
    "requires_credentials": False,
    "metadata_json": {
        "role": "official_historical_fuel_rupture_outcome_stream",
        "archive_available_from": ANNUAL_ARCHIVE_AVAILABLE_FROM,
        "license": "Licence Ouverte / Open Licence",
        "temporary_ruptures_only": True,
        "definitive_non_distribution_excluded": True,
        "historical_trigger_source": False,
    },
}


def _local_name(tag: str) -> str:
    return str(tag).split("}")[-1]


def _fuel_name(element: ET.Element) -> str:
    fuel_id = str(element.attrib.get("id") or "").strip()
    return str(
        element.attrib.get("fuel")
        or element.attrib.get("nom")
        or FUEL_NAMES.get(fuel_id)
        or fuel_id
    ).strip()


def _year_bounds(year: int) -> tuple[datetime, datetime]:
    return (
        datetime(year, 1, 1, tzinfo=timezone.utc),
        datetime(year + 1, 1, 1, tzinfo=timezone.utc),
    )


def _archive_url(year: int) -> str:
    return f"{ANNUAL_ARCHIVE_BASE_URL}/{year}"


def _day_end(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _aggregate_archive(
    content: bytes,
    *,
    year: int,
    departments: set[str],
) -> dict:
    if len(content) > MAX_ZIP_BYTES:
        raise ValueError("fuel annual archive ZIP exceeds configured compressed-size limit")

    year_start, year_end = _year_bounds(year)
    offering: dict[tuple[str, str], set[str]] = defaultdict(set)
    active_by_day: dict[tuple[date, str, str], set[str]] = defaultdict(set)
    stations: set[str] = set()
    skipped_scope = 0
    temporary_intervals = 0

    try:
        with ZipFile(BytesIO(content)) as archive:
            members = [item for item in archive.infolist() if item.filename.lower().endswith(".xml")]
            if len(members) != 1:
                raise ValueError("fuel annual archive ZIP must contain exactly one XML document")
            member = members[0]
            if member.file_size > MAX_XML_BYTES:
                raise ValueError("fuel annual archive XML exceeds configured uncompressed-size limit")

            with archive.open(member) as probe:
                head = probe.read(4096).upper()
            if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
                raise ValueError("fuel annual archive XML contains forbidden DTD/entity declarations")

            with archive.open(member) as stream:
                try:
                    iterator = ET.iterparse(stream, events=("end",))
                    for _, pdv in iterator:
                        if _local_name(pdv.tag) != "pdv":
                            continue

                        station_id = str(pdv.attrib.get("id") or "").strip()
                        department = _department_from_postal(str(pdv.attrib.get("cp") or ""))
                        if not station_id or department is None:
                            skipped_scope += 1
                            pdv.clear()
                            continue
                        if departments and department not in departments:
                            pdv.clear()
                            continue

                        stations.add(station_id)

                        for child in list(pdv):
                            tag = _local_name(child.tag)
                            fuel = _fuel_name(child)
                            if not fuel:
                                continue

                            if tag == "prix":
                                offering[(department, fuel)].add(station_id)
                                continue

                            if tag != "rupture":
                                continue
                            kind = str(child.attrib.get("type") or "").strip().lower()
                            if kind != "temporaire":
                                continue

                            start = _parse_feed_datetime(child.attrib.get("debut"))
                            end = _parse_feed_datetime(child.attrib.get("fin"))
                            if start is None:
                                continue
                            if end is None:
                                end = year_end
                            if end <= year_start or start >= year_end or end <= start:
                                continue

                            clipped_start = max(start, year_start)
                            clipped_end = min(end, year_end)
                            offering[(department, fuel)].add(station_id)
                            temporary_intervals += 1

                            day = clipped_start.date()
                            while datetime.combine(day, time.min, tzinfo=timezone.utc) < clipped_end:
                                active_by_day[(day, department, fuel)].add(station_id)
                                day += timedelta(days=1)

                        pdv.clear()
                except ET.ParseError as exc:
                    raise ValueError("fuel annual archive XML cannot be parsed") from exc
    except BadZipFile as exc:
        raise ValueError("fuel annual archive is not a valid ZIP archive") from exc

    rows = []
    for (day, department, fuel), rupture_stations in sorted(active_by_day.items()):
        reporting = len(offering[(department, fuel)])
        temporary = len(rupture_stations)
        if reporting <= 0:
            continue
        rows.append({
            "day": day.isoformat(),
            "department": department,
            "fuel": fuel,
            "reporting_stations_annual_offering_set": reporting,
            "stations_with_temporary_rupture_during_day": temporary,
            "daily_temporary_rupture_station_share": round(temporary / reporting, 6),
            "observation_available_no_earlier_than": _day_end(day).isoformat(),
        })

    return {
        "year": year,
        "stations_in_scope": len(stations),
        "stations_skipped_for_scope": skipped_scope,
        "temporary_intervals": temporary_intervals,
        "departments": sorted({department for department, _ in offering}),
        "daily_rows": rows,
        "metric_semantics": (
            "share of the annual station/fuel offering set that had any temporary rupture "
            "overlapping the calendar day; this is not an instantaneous concurrent stockout rate"
        ),
        "definitive_non_distribution_excluded": True,
    }


class HorizonFuelHistoricalBackfillService:
    ENGINE_VERSION = "horizon-fr-fuel-historical-outcome-v0.1"
    ADAPTER_KIND = SOURCE_SPEC["adapter_kind"]
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        row = self.db.query(HorizonSource).filter(HorizonSource.source_key == SOURCE_KEY).one_or_none()
        if row is None:
            row = HorizonSource(source_key=SOURCE_KEY, enabled=True, **SOURCE_SPEC)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        else:
            for key in ("source_class", "adapter_kind", "base_locator"):
                if getattr(row, key) != SOURCE_SPEC[key]:
                    raise ValueError(f"fuel annual archive source {key} differs from approved adapter contract")
        if not row.enabled:
            raise ValueError("French fuel annual archive source is disabled")
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
        request: HorizonFuelHistoricalBackfillRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        current_year = datetime.now(timezone.utc).year
        if request.year < ANNUAL_ARCHIVE_AVAILABLE_FROM:
            raise ValueError(f"fuel annual archive is available from {ANNUAL_ARCHIVE_AVAILABLE_FROM}")
        if request.year > current_year:
            raise ValueError("fuel annual archive year cannot be in the future")

        source = self._source()
        url = _archive_url(request.year)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(120.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/zip"},
            )

        try:
            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"French fuel annual archive fetch failed: {str(exc)[:300]}") from exc
            if response.url.host not in ALLOWED_DOWNLOAD_HOSTS:
                raise RuntimeError("French fuel annual archive redirected outside the approved host")
            content = response.content
        finally:
            if owned_client:
                client.close()

        archive_hash = sha256(content).hexdigest()
        request_snapshot = request.model_dump(mode="json")
        run_key = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "adapter_kind": self.ADAPTER_KIND,
            "source_id": source.id,
            "archive_url": url,
            "archive_hash": archive_hash,
            "request": request_snapshot,
        })
        existing = self.db.query(HorizonHistoricalBackfillRun).filter(
            HorizonHistoricalBackfillRun.run_key == run_key
        ).one_or_none()
        if existing is not None:
            return self._serialize_run(existing, replayed=True)

        aggregate = _aggregate_archive(
            content,
            year=request.year,
            departments=set(request.departments),
        )
        qualifying = [
            row for row in aggregate["daily_rows"]
            if row["reporting_stations_annual_offering_set"] >= request.min_reporting_stations
            and row["stations_with_temporary_rupture_during_day"] >= request.min_temporary_ruptures
            and row["daily_temporary_rupture_station_share"] >= request.min_rupture_rate
        ]
        truncated = len(qualifying) > request.max_observations
        selected = qualifying[: request.max_observations]

        source_service = HorizonSourceService(self.db)
        created_ids: list[int] = []
        replayed_ids: list[int] = []
        for item in selected:
            available_at = datetime.fromisoformat(item["observation_available_no_earlier_than"])
            digest = sha256(
                (
                    f"{archive_hash}|{item['day']}|{item['department']}|{item['fuel']}|"
                    f"{item['reporting_stations_annual_offering_set']}|"
                    f"{item['stations_with_temporary_rupture_during_day']}"
                ).encode("utf-8")
            ).hexdigest()[:56]
            observation = HorizonObservationIngest(
                external_key=f"fuel-annual-pressure:{digest}",
                observation_type="official_fuel_rupture_archive_daily",
                title=(
                    f"Ruptures temporaires carburant — {item['fuel']} — "
                    f"département {item['department']} — {item['day']}"
                ),
                summary=(
                    "Agrégat historique officiel des stations ayant déclaré au moins une rupture "
                    "temporaire durant la journée."
                ),
                source_url=url,
                geography=["FR", f"DEP:{item['department']}"],
                canonical_facts={
                    "outcome_signal_type": "fuel_stockout_pressure",
                    "year": request.year,
                    **item,
                    "thresholds": {
                        "min_reporting_stations": request.min_reporting_stations,
                        "min_temporary_ruptures": request.min_temporary_ruptures,
                        "min_rupture_rate": request.min_rupture_rate,
                    },
                    "metric_semantics": aggregate["metric_semantics"],
                    "definitive_non_distribution_excluded": True,
                },
                raw_metadata={
                    "engine": self.ENGINE_VERSION,
                    "adapter": self.ADAPTER_KIND,
                    "archive_hash": archive_hash,
                    "source_format": "zip+xml",
                    "historical_timestamp_semantics": (
                        "observed_at_is_calendar_day_end_for_conservative_daily_outcome_replay"
                    ),
                    "archive_retrieval_time_is_not_used_as_historical_event_time": True,
                    "does_not_measure": [
                        "cause_of_rupture",
                        "panic_buying",
                        "queue_behavior",
                        "instantaneous_concurrent_stockout_rate",
                    ],
                },
                event_time=available_at,
                published_at=available_at,
                observed_at=available_at,
            )
            row, created = source_service.ingest_observation(source, observation)
            (created_ids if created else replayed_ids).append(row.id)

        year_start, year_end = _year_bounds(request.year)
        now = datetime.now(timezone.utc)
        completed_year = request.year < current_year
        coverage_end = year_end if completed_year else min(now, year_end)
        coverage_complete = completed_year and not truncated
        department_tokens = [f"DEP:{item}" for item in aggregate["departments"]]
        coverage = HorizonHistoricalCoverageService(self.db).record_interval(
            source,
            coverage_kind="signal",
            event_types=["fuel_supply_disruption", "supply_disruption"],
            signal_types=["fuel_stockout_pressure"],
            geography=["FR", *department_tokens],
            start_at=year_start,
            end_at=coverage_end,
            completeness="complete" if coverage_complete else "partial",
            basis="official_fuel_annual_archive_all_rows_parsed",
            provenance={
                "engine": self.ENGINE_VERSION,
                "archive_url": url,
                "archive_hash": archive_hash,
                "archive_available_from": ANNUAL_ARCHIVE_AVAILABLE_FROM,
                "completed_calendar_year": completed_year,
                "qualifying_daily_rows": len(qualifying),
                "selected_daily_rows": len(selected),
                "truncated_by_max_observations": truncated,
                "metric_semantics": aggregate["metric_semantics"],
                "denominator_semantics": "annual station/fuel offering set",
                "temporary_ruptures_only": True,
                "definitive_non_distribution_excluded": True,
                "historical_trigger_replay_provided": False,
            },
        )

        result = {
            "engine": self.ENGINE_VERSION,
            "adapter": self.ADAPTER_KIND,
            "source_key": source.source_key,
            "year": request.year,
            "archive_url": url,
            "archive_hash": archive_hash,
            "stations_in_scope": aggregate["stations_in_scope"],
            "temporary_intervals": aggregate["temporary_intervals"],
            "daily_rows_considered": len(aggregate["daily_rows"]),
            "qualifying_pressure_days": len(qualifying),
            "observations_created": len(created_ids),
            "observations_replayed": len(replayed_ids),
            "observation_ids": created_ids + replayed_ids,
            "truncated_by_max_observations": truncated,
            "signal_coverage_interval_id": coverage.id,
            "signal_coverage_complete": coverage.completeness == "complete",
            "metric_semantics": aggregate["metric_semantics"],
            "critical_semantics": {
                "outcome_replay_only": True,
                "historical_trigger_replay_provided": False,
                "daily_metric_is_instantaneous_stockout_rate": False,
                "definitive_non_distribution_excluded": True,
                "complete_coverage_required_for_negative_label": True,
                "provider_failure_is_negative_evidence": False,
                "numeric_probabilities_enabled": False,
            },
        }
        run = HorizonHistoricalBackfillRun(
            run_key=run_key,
            engine_version=self.ENGINE_VERSION,
            adapter_kind=self.ADAPTER_KIND,
            source_id=source.id,
            requested_start_at=year_start.replace(tzinfo=None),
            requested_end_at=coverage_end.replace(tzinfo=None),
            request_snapshot=request_snapshot,
            result_snapshot=result,
            status="completed" if not truncated else "completed_partial",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return self._serialize_run(run, replayed=False)
