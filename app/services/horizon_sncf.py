from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from ..horizon_convergence_schemas import HorizonSncfPollRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService


SNCF_SIRI_ENDPOINT = "https://proxy.transport.data.gouv.fr/resource/sncf-siri-lite-situation-exchange"


def _text(node: ET.Element, name: str) -> str:
    found = node.find(f".//{{*}}{name}")
    return (found.text or "").strip() if found is not None else ""


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class HorizonSncfService:
    ENGINE_VERSION = "horizon-sncf-siri-sx-lite-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key="sncf-service-alerts",
                name="SNCF Voyageurs realtime service alerts",
                source_class="official_primary",
                adapter_kind="sncf_siri_sx_lite_xml",
                domains=["transport", "rail", "operational_disruption", "realtime"],
                geography=["FR"],
                base_locator=SNCF_SIRI_ENDPOINT,
                trust_weight=0.93,
                refresh_seconds=120,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "official_rail_operational_disruption",
                    "evidence_roles": ["confirmation", "operational_impact"],
                    "provider": "SNCF Voyageurs",
                    "format": "SIRI_SX_Lite",
                    "provider_refresh_seconds": 120,
                    "scope": ["TGV", "Intercites", "TER", "OUIGO"],
                    "excluded_scope": ["Transilien"],
                },
            )
        )
        if not source.enabled:
            raise ValueError("SNCF realtime source is disabled")
        return source

    @staticmethod
    def _situation_payload(node: ET.Element) -> dict:
        situation_number = _text(node, "SituationNumber") or _text(node, "ParticipantRef")
        summary = _text(node, "Summary") or _text(node, "Description")
        description = _text(node, "Description")
        creation_time = _text(node, "CreationTime")
        start_time = _text(node, "StartTime")
        end_time = _text(node, "EndTime")
        progress = _text(node, "Progress")
        severity = _text(node, "Severity")
        consequence = _text(node, "Consequence")
        operator = _text(node, "OperatorRef")
        line = _text(node, "LineRef")
        stop = _text(node, "StopPointRef")
        vehicle_journey = _text(node, "VehicleJourneyRef")
        return {
            "situation_number": situation_number,
            "summary": summary,
            "description": description,
            "creation_time": creation_time,
            "start_time": start_time,
            "end_time": end_time,
            "progress": progress,
            "severity": severity,
            "consequence": consequence,
            "operator_ref": operator,
            "line_ref": line,
            "stop_point_ref": stop,
            "vehicle_journey_ref": vehicle_journey,
        }

    def poll(
        self,
        request: HorizonSncfPollRequest,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        source = self._source()
        as_of = observed_at or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/xml,text/xml"},
            )
        try:
            response = client.get(SNCF_SIRI_ENDPOINT)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (httpx.HTTPError, ET.ParseError) as exc:
            raise RuntimeError(f"SNCF realtime poll failed: {str(exc)[:300]}") from exc
        finally:
            if owned_client:
                client.close()

        situations = root.findall(".//{*}PtSituationElement")
        if not situations:
            situations = root.findall(".//{*}Situation")

        source_service = HorizonSourceService(self.db)
        observation_ids: list[int] = []
        replayed_ids: list[int] = []
        candidate_ids: list[int] = []
        event_ids: list[int] = []
        skipped = 0
        for node in situations[: request.max_situations]:
            facts = self._situation_payload(node)
            situation_number = facts["situation_number"]
            if not situation_number or not (facts["summary"] or facts["description"]):
                skipped += 1
                continue
            stable = {
                key: facts[key]
                for key in (
                    "situation_number", "summary", "description", "creation_time", "start_time", "end_time",
                    "progress", "severity", "consequence", "operator_ref", "line_ref", "stop_point_ref",
                    "vehicle_journey_ref",
                )
            }
            version_hash = sha256(repr(stable).encode("utf-8")).hexdigest()[:32]
            external_key = f"sncf-siri:{situation_number}:{version_hash}"[:192]
            existing = self.db.query(HorizonRawObservation).filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.external_key == external_key,
            ).one_or_none()
            if existing is None:
                published_at = _parse_time(facts["creation_time"])
                start_at = _parse_time(facts["start_time"])
                observation = HorizonObservationIngest(
                    external_key=external_key,
                    observation_type="official_rail_service_disruption",
                    title=(facts["summary"] or facts["description"] or "Perturbation SNCF")[:255],
                    summary=facts["description"][:4000],
                    source_url=SNCF_SIRI_ENDPOINT,
                    geography=["FR"],
                    canonical_facts=facts,
                    raw_metadata={
                        "engine": self.ENGINE_VERSION,
                        "format": "SIRI_SX_Lite",
                        "upstream_version_hash": version_hash,
                        "operational_fact": True,
                    },
                    event_time=start_at or published_at,
                    published_at=published_at,
                    observed_at=as_of,
                )
                observation_row, _ = source_service.ingest_observation(source, observation)
                observation_ids.append(observation_row.id)
            else:
                observation_row = existing
                replayed_ids.append(existing.id)

            candidate = source_service.build_candidate(
                HorizonCandidateBuild(
                    observation_ids=[observation_row.id],
                    event_type="rail_transport_disruption",
                    title=(facts["summary"] or facts["description"] or "Perturbation SNCF")[:255],
                    geography=["FR"],
                    normalized_facts={
                        "provider": "sncf",
                        "situation_number": situation_number,
                        "line_ref": facts["line_ref"],
                        "stop_point_ref": facts["stop_point_ref"],
                        "vehicle_journey_ref": facts["vehicle_journey_ref"],
                        "severity": facts["severity"],
                        "progress": facts["progress"],
                        "operational_impact": True,
                    },
                    normalizer_version=self.ENGINE_VERSION,
                )
            )
            candidate_ids.append(candidate.id)
            event = source_service.promote_candidate(candidate)
            event_ids.append(event.id)

        return {
            "engine": self.ENGINE_VERSION,
            "source_key": source.source_key,
            "situations_received": len(situations),
            "situations_skipped": skipped,
            "new_observations": len(set(observation_ids)),
            "replayed_observations": len(set(replayed_ids)),
            "candidates_created_or_reused": len(set(candidate_ids)),
            "promoted_events_created_or_reused": len(set(event_ids)),
            "event_ids": sorted(set(event_ids)),
            "critical_semantics": {
                "source_is_official_primary": True,
                "feed_is_operational_fact": True,
                "transport_disruption_is_behavioral_outcome": False,
                "severity_is_probability": False,
            },
        }
