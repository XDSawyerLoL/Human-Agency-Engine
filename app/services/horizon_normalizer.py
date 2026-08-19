from __future__ import annotations

from sqlalchemy.orm import Session

from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild
from .horizon_sources import HorizonSourceService


METEOFRANCE_PHENOMENA = {
    "1": ("strong_wind", "vent"),
    "2": ("heavy_rain", "pluie"),
    "3": ("thunderstorm", "orages"),
    "4": ("flood", "crues"),
    "5": ("snow_ice", "neige/verglas"),
    "6": ("extreme_heat", "canicule"),
    "7": ("extreme_cold", "grand froid"),
    "8": ("avalanche", "avalanches"),
    "9": ("coastal_flood", "vagues-submersion"),
}
COLOR_NAMES = {1: "vert", 2: "jaune", 3: "orange", 4: "rouge"}


class HorizonMeteoFranceNormalizer:
    VERSION = "meteofrance-v6-personal-scope-v0.1"

    def __init__(self, db: Session):
        self.db = db

    def _observation(self, observation_id: int) -> tuple[HorizonRawObservation, HorizonSource]:
        observation = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == observation_id
        ).one_or_none()
        if observation is None:
            raise ValueError("Météo-France raw observation not found")
        source = self.db.query(HorizonSource).filter(HorizonSource.id == observation.source_id).one()
        if source.source_key != "meteofrance-vigilance" or source.source_class != "official_primary":
            raise ValueError("observation is not from the approved Météo-France official-primary source")
        if observation.observation_type != "official_weather_vigilance":
            raise ValueError("observation is not a Météo-France Vigilance map snapshot")
        return observation, source

    @staticmethod
    def _scope(domain_id: str) -> tuple[str, dict]:
        normalized = domain_id.strip().upper()
        is_department = (
            normalized in {"2A", "2B"}
            or (normalized.isdigit() and 1 <= len(normalized) <= 3)
        )
        state_key = "location.department" if is_department else "location.coastal_zone"
        return (
            "department" if is_department else "coastal_zone",
            {
                "all": [
                    {
                        "state_key": state_key,
                        "value_path": "code",
                        "operator": "equals",
                        "value": normalized,
                    }
                ]
            },
        )

    def normalize(self, observation_id: int) -> dict:
        observation, _ = self._observation(observation_id)
        facts = observation.canonical_facts or {}
        alerts = facts.get("alerts", [])
        if not isinstance(alerts, list):
            raise ValueError("Météo-France observation has invalid alert structure")

        source_service = HorizonSourceService(self.db)
        normalized = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            domain_id = str(alert.get("domain_id") or "").strip().upper()
            if not domain_id:
                continue
            domain_kind, personal_scope = self._scope(domain_id)
            period = {
                "echeance": alert.get("echeance"),
                "begin_validity_time": alert.get("begin_validity_time"),
                "end_validity_time": alert.get("end_validity_time"),
            }
            phenomena = alert.get("phenomena", [])
            if not isinstance(phenomena, list):
                phenomena = []

            for phenomenon in phenomena:
                if not isinstance(phenomenon, dict):
                    continue
                phenomenon_id = str(phenomenon.get("phenomenon_id") or "").strip()
                event_type, phenomenon_name = METEOFRANCE_PHENOMENA.get(
                    phenomenon_id,
                    ("weather_hazard", f"phénomène {phenomenon_id or 'inconnu'}"),
                )
                color_id = int(phenomenon.get("max_color_id") or alert.get("max_color_id") or 0)
                if color_id < 2:
                    continue
                color_name = COLOR_NAMES.get(color_id, f"niveau-{color_id}")
                normalized_facts = {
                    "normalization_source": "meteofrance-vigilance-v6",
                    "source_observation_id": observation.id,
                    "snapshot_id": facts.get("snapshot_id"),
                    "domain_id": domain_id,
                    "domain_kind": domain_kind,
                    "phenomenon_id": phenomenon_id,
                    "phenomenon_name": phenomenon_name,
                    "color_id": color_id,
                    "color_name": color_name,
                    "period": period,
                    "timelaps": phenomenon.get("timelaps", []),
                    "personal_scope": personal_scope,
                }
                candidate = source_service.build_candidate(
                    HorizonCandidateBuild(
                        observation_ids=[observation.id],
                        event_type=event_type,
                        title=(
                            f"Vigilance Météo-France {color_name} {phenomenon_name} "
                            f"— zone {domain_id}"
                        ),
                        geography=["FR"],
                        normalized_facts=normalized_facts,
                        normalizer_version=self.VERSION,
                    )
                )
                event = source_service.promote_candidate(candidate)
                normalized.append(
                    {
                        "candidate_id": candidate.id,
                        "event_id": event.id,
                        "event_key": event.event_key,
                        "event_type": event.event_type,
                        "title": event.title,
                        "domain_id": domain_id,
                        "domain_kind": domain_kind,
                        "phenomenon_id": phenomenon_id,
                        "phenomenon_name": phenomenon_name,
                        "color_id": color_id,
                        "color_name": color_name,
                        "personal_scope": personal_scope,
                        "official_primary_promoted": True,
                    }
                )

        return {
            "source_observation_id": observation.id,
            "normalizer_version": self.VERSION,
            "normalized_event_count": len(normalized),
            "events": normalized,
            "scope_preserved": True,
            "raw_facts_rewritten": False,
        }

    def normalize_latest(self) -> dict:
        source = self.db.query(HorizonSource).filter(
            HorizonSource.source_key == "meteofrance-vigilance"
        ).one_or_none()
        if source is None:
            HorizonSourceService(self.db).sync_builtin_sources()
            source = self.db.query(HorizonSource).filter(
                HorizonSource.source_key == "meteofrance-vigilance"
            ).one()
        observation = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.observation_type == "official_weather_vigilance",
        ).order_by(HorizonRawObservation.observed_at.desc(), HorizonRawObservation.id.desc()).first()
        if observation is None:
            return {
                "skipped": True,
                "reason": "no Météo-France Vigilance observation available",
                "normalized_event_count": 0,
                "events": [],
            }
        return self.normalize(observation.id)
