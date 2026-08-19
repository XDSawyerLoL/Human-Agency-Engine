from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

import httpx
from sqlalchemy.orm import Session

from ..horizon_fuel_schemas import HorizonFuelNormalizeRequest
from ..horizon_models import HorizonSocialSignal
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest
from .horizon_sources import HorizonSourceService


FUEL_RUPTURE_URL = "https://donnees.roulez-eco.fr/opendata/instantane_ruptures"
ALLOWED_DOWNLOAD_HOSTS = {"donnees.roulez-eco.fr"}
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024

SOURCE_KEY = "fr-fuel-ruptures-live"
SOURCE_SPEC = {
    "name": "Prix Carburants — flux instantané avec ruptures",
    "source_class": "official_primary",
    "adapter_kind": "fr_fuel_ruptures_zip_xml",
    "domains": ["fuel", "supply", "mobility"],
    "geography": ["FR"],
    "base_locator": FUEL_RUPTURE_URL,
    "trust_weight": 0.96,
    "refresh_seconds": 600,
    "requires_credentials": False,
    "metadata_json": {
        "role": "official_operational_station_report_feed",
        "license": "Licence Ouverte / Open Licence",
        "temporary_ruptures_only_for_crisis_signal": True,
        "definitive_non_distribution_excluded": True,
    },
}

FUEL_NAMES = {
    "1": "Gazole",
    "2": "SP95",
    "3": "E85",
    "4": "GPLc",
    "5": "E10",
    "6": "SP98",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_feed_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _department_from_postal(cp: str) -> str | None:
    value = str(cp or "").strip()
    if len(value) != 5 or not value.isdigit():
        return None
    if value.startswith("20"):
        # Postal codes do not distinguish 2A/2B reliably enough for a hard
        # personal-scope gate. Skip Corsica until an INSEE/commune mapping is added.
        return None
    if value.startswith(("97", "98")):
        return value[:3]
    return value[:2]


def _active_temporary(rupture: ET.Element, now: datetime) -> bool:
    if str(rupture.attrib.get("type") or "").strip().lower() != "temporaire":
        return False
    start = _parse_feed_datetime(rupture.attrib.get("debut"))
    end = _parse_feed_datetime(rupture.attrib.get("fin"))
    if start is not None and start > now:
        return False
    if end is not None and end <= now:
        return False
    return True


def _fuel_identity(element: ET.Element) -> tuple[str, str]:
    fuel_id = str(element.attrib.get("id") or "").strip()
    name = str(
        element.attrib.get("fuel")
        or element.attrib.get("nom")
        or FUEL_NAMES.get(fuel_id)
        or fuel_id
    ).strip()
    return fuel_id, name


def _read_xml_from_zip(content: bytes) -> bytes:
    if len(content) > MAX_ZIP_BYTES:
        raise ValueError("fuel rupture ZIP exceeds configured compressed-size limit")
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = [item for item in archive.infolist() if item.filename.lower().endswith(".xml")]
            if len(members) != 1:
                raise ValueError("fuel rupture ZIP must contain exactly one XML document")
            member = members[0]
            if member.file_size > MAX_XML_BYTES:
                raise ValueError("fuel rupture XML exceeds configured uncompressed-size limit")
            xml_bytes = archive.read(member)
    except BadZipFile as exc:
        raise ValueError("fuel rupture feed is not a valid ZIP archive") from exc
    upper = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("fuel rupture XML contains forbidden DTD/entity declarations")
    return xml_bytes


def _aggregate(xml_bytes: bytes, now: datetime) -> dict:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("fuel rupture XML cannot be parsed") from exc

    offered: dict[tuple[str, str], set[str]] = defaultdict(set)
    temporary: dict[tuple[str, str], set[str]] = defaultdict(set)
    unsupported_scope = 0
    station_count = 0

    for pdv in root.findall(".//pdv"):
        station_id = str(pdv.attrib.get("id") or "").strip()
        department = _department_from_postal(str(pdv.attrib.get("cp") or ""))
        if not station_id or department is None:
            unsupported_scope += 1
            continue
        station_count += 1

        permanent_fuels: set[str] = set()
        temp_fuels: set[str] = set()
        for rupture in pdv.findall("rupture"):
            fuel_id, fuel_name = _fuel_identity(rupture)
            fuel_key = fuel_id or fuel_name
            if not fuel_key:
                continue
            kind = str(rupture.attrib.get("type") or "").strip().lower()
            if kind == "definitive":
                permanent_fuels.add(fuel_key)
            elif _active_temporary(rupture, now):
                temp_fuels.add(fuel_key)
                temporary[(department, fuel_key)].add(station_id)

        for price in pdv.findall("prix"):
            fuel_id, fuel_name = _fuel_identity(price)
            fuel_key = fuel_id or fuel_name
            if fuel_key and fuel_key not in permanent_fuels:
                offered[(department, fuel_key)].add(station_id)

        # A temporarily unavailable fuel is still part of the station's normal
        # offering and therefore belongs in the denominator.
        for fuel_key in temp_fuels:
            offered[(department, fuel_key)].add(station_id)

    department_fuels: dict[str, dict] = {}
    national_accumulator: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"offered": set(), "temporary": set()}
    )
    all_keys = sorted(set(offered) | set(temporary))
    for department, fuel_key in all_keys:
        stations = offered[(department, fuel_key)]
        ruptures = temporary[(department, fuel_key)]
        denominator = len(stations)
        rupture_count = len(ruptures)
        if denominator <= 0:
            continue
        fuel_name = FUEL_NAMES.get(fuel_key, fuel_key)
        rate = rupture_count / denominator
        department_fuels.setdefault(department, {})[fuel_name] = {
            "fuel_id": fuel_key,
            "reporting_stations": denominator,
            "temporary_ruptures": rupture_count,
            "temporary_rupture_rate": round(rate, 6),
        }
        national_accumulator[fuel_name]["offered"].update(
            f"{department}:{item}" for item in stations
        )
        national_accumulator[fuel_name]["temporary"].update(
            f"{department}:{item}" for item in ruptures
        )

    national = {}
    for fuel_name, groups in sorted(national_accumulator.items()):
        denominator = len(groups["offered"])
        rupture_count = len(groups["temporary"])
        national[fuel_name] = {
            "reporting_stations": denominator,
            "temporary_ruptures": rupture_count,
            "temporary_rupture_rate": round(rupture_count / denominator, 6) if denominator else 0.0,
        }

    return {
        "station_count_in_supported_scope": station_count,
        "stations_skipped_for_scope": unsupported_scope,
        "department_fuels": department_fuels,
        "national": national,
        "definitive_non_distribution_excluded": True,
        "temporary_ruptures_only": True,
    }


class HorizonFuelService:
    ENGINE_VERSION = "horizon-fr-fuel-rupture-v0.1"
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
            immutable_identity = {
                "source_class": SOURCE_SPEC["source_class"],
                "adapter_kind": SOURCE_SPEC["adapter_kind"],
                "base_locator": SOURCE_SPEC["base_locator"],
            }
            for key, expected in immutable_identity.items():
                if getattr(row, key) != expected:
                    raise ValueError(f"fuel source {key} differs from approved adapter contract")
        if not row.enabled:
            raise ValueError("French fuel rupture source is disabled")
        return row

    def poll(self, *, client: httpx.Client | None = None) -> dict:
        source = self._source()
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/zip"},
            )
        try:
            try:
                response = client.get(FUEL_RUPTURE_URL)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"French fuel rupture poll failed: {str(exc)[:300]}") from exc
            if response.url.host not in ALLOWED_DOWNLOAD_HOSTS:
                raise RuntimeError("French fuel rupture feed redirected outside the approved host")
            content = response.content
        finally:
            if owned_client:
                client.close()

        feed_hash = sha256(content).hexdigest()
        external_key = f"fuel-ruptures:{feed_hash[:48]}"
        existing = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.external_key == external_key,
        ).one_or_none()
        if existing is not None:
            return {
                "source_key": source.source_key,
                "new_observations": 0,
                "replayed_observations": 1,
                "observation_id": existing.id,
                "feed_hash": feed_hash,
                "temporary_ruptures_only": True,
                "promoted_events": 0,
            }

        now = _utc_now()
        xml_bytes = _read_xml_from_zip(content)
        aggregate = _aggregate(xml_bytes, now)
        observation = HorizonObservationIngest(
            external_key=external_key,
            observation_type="official_fuel_rupture_snapshot",
            title="France — flux instantané officiel des ruptures carburants",
            summary="Agrégat des ruptures temporaires actives déclarées dans le flux officiel.",
            source_url=FUEL_RUPTURE_URL,
            geography=["FR"],
            canonical_facts={
                "feed_hash": feed_hash,
                "engine": self.ENGINE_VERSION,
                **aggregate,
            },
            raw_metadata={
                "compressed_bytes": len(content),
                "xml_bytes": len(xml_bytes),
                "source_format": "zip+xml",
                "raw_station_rows_persisted": False,
            },
            event_time=now,
            published_at=now,
            observed_at=now,
        )
        row, created = HorizonSourceService(self.db).ingest_observation(source, observation)
        return {
            "source_key": source.source_key,
            "new_observations": 1 if created else 0,
            "replayed_observations": 0 if created else 1,
            "observation_id": row.id,
            "feed_hash": feed_hash,
            "temporary_ruptures_only": True,
            "stations": aggregate["station_count_in_supported_scope"],
            "promoted_events": 0,
        }

    def normalize_latest(self, request: HorizonFuelNormalizeRequest) -> dict:
        source = self._source()
        observation = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.observation_type == "official_fuel_rupture_snapshot",
        ).order_by(HorizonRawObservation.observed_at.desc(), HorizonRawObservation.id.desc()).first()
        if observation is None:
            return {
                "skipped": True,
                "reason": "no official fuel rupture observation available",
                "events_created_or_reused": 0,
                "events": [],
            }

        facts = observation.canonical_facts or {}
        department_fuels = facts.get("department_fuels", {})
        if not isinstance(department_fuels, dict):
            raise ValueError("fuel rupture observation contains invalid department aggregate")

        results = []
        source_service = HorizonSourceService(self.db)
        for department, fuels in sorted(department_fuels.items()):
            if not isinstance(fuels, dict):
                continue
            for fuel_name, metric in sorted(fuels.items()):
                if not isinstance(metric, dict):
                    continue
                stations = int(metric.get("reporting_stations") or 0)
                temporary = int(metric.get("temporary_ruptures") or 0)
                rate = float(metric.get("temporary_rupture_rate") or 0.0)
                if (
                    stations < request.min_reporting_stations
                    or temporary < request.min_temporary_ruptures
                    or rate < request.min_rupture_rate
                ):
                    continue

                normalized_facts = {
                    "normalization_source": SOURCE_KEY,
                    "source_observation_id": observation.id,
                    "feed_hash": facts.get("feed_hash"),
                    "department": department,
                    "fuel": fuel_name,
                    "reporting_stations": stations,
                    "temporary_ruptures": temporary,
                    "temporary_rupture_rate": rate,
                    "thresholds": request.model_dump(),
                    "personal_scope": {
                        "all": [
                            {
                                "state_key": "location.department",
                                "value_path": "code",
                                "operator": "equals",
                                "value": department,
                            }
                        ]
                    },
                }
                candidate = source_service.build_candidate(
                    HorizonCandidateBuild(
                        observation_ids=[observation.id],
                        event_type="fuel_supply_disruption",
                        title=(
                            f"Ruptures temporaires de {fuel_name} — département {department} "
                            f"({temporary}/{stations})"
                        ),
                        geography=["FR"],
                        normalized_facts=normalized_facts,
                        normalizer_version=self.ENGINE_VERSION,
                    )
                )
                event = source_service.promote_candidate(candidate)

                signal_key = "fuel-stock:" + sha256(
                    f"{event.id}|{facts.get('feed_hash')}|{fuel_name}|{department}".encode("utf-8")
                ).hexdigest()[:48]
                signal = self.db.query(HorizonSocialSignal).filter(
                    HorizonSocialSignal.signal_key == signal_key
                ).one_or_none()
                signal_created = False
                if signal is None:
                    signal = HorizonSocialSignal(
                        event_id=event.id,
                        signal_key=signal_key,
                        signal_type="stock_availability",
                        source=SOURCE_KEY,
                        geography=["FR", f"DEP:{department}"],
                        value=round(1.0 - rate, 6),
                        baseline=1.0,
                        normalized_score=round(min(10.0, max(0.1, rate * 10.0)), 4),
                        direction="down",
                        reliability=0.96,
                        evidence={
                            "engine": self.ENGINE_VERSION,
                            "material_observation": True,
                            "reporting_stations": stations,
                            "temporary_ruptures": temporary,
                            "temporary_rupture_rate": rate,
                            "definitive_non_distribution_excluded": True,
                            "does_not_measure": [
                                "panic_buying",
                                "queue_behavior",
                                "cause_of_rupture",
                            ],
                        },
                        observed_at=observation.observed_at,
                    )
                    self.db.add(signal)
                    self.db.commit()
                    self.db.refresh(signal)
                    signal_created = True

                results.append(
                    {
                        "candidate_id": candidate.id,
                        "event_id": event.id,
                        "event_key": event.event_key,
                        "department": department,
                        "fuel": fuel_name,
                        "reporting_stations": stations,
                        "temporary_ruptures": temporary,
                        "temporary_rupture_rate": rate,
                        "personal_scope": normalized_facts["personal_scope"],
                        "stock_signal_id": signal.id,
                        "stock_signal_created": signal_created,
                    }
                )

        return {
            "source_observation_id": observation.id,
            "normalizer_version": self.ENGINE_VERSION,
            "events_created_or_reused": len(results),
            "events": results,
            "temporary_ruptures_only": True,
            "definitive_non_distribution_excluded": True,
            "raw_station_rows_persisted": False,
        }
