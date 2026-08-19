from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild
from .horizon_sources import HorizonSourceService


METEOALARM_WEATHER_MAP = (
    (("heat", "high temperature", "hot"), "extreme_heat"),
    (("cold", "low temperature", "frost"), "extreme_cold"),
    (("wind", "gale"), "strong_wind"),
    (("thunderstorm", "storm", "lightning"), "thunderstorm"),
    (("rain", "precipitation"), "heavy_rain"),
    (("flood", "inundation"), "flood"),
    (("snow", "ice", "freezing rain"), "snow_ice"),
    (("avalanche",), "avalanche"),
    (("coastal", "storm surge", "wave"), "coastal_flood"),
    (("fog",), "fog"),
)


def _meteoalarm_event_type(facts: dict, title: str) -> str:
    text = " ".join(
        str(value or "")
        for value in (facts.get("event"), title, facts.get("area"))
    ).lower()
    for needles, event_type in METEOALARM_WEATHER_MAP:
        if any(needle in text for needle in needles):
            return event_type
    event = str(facts.get("event") or "weather_warning").lower().strip()
    suffix = re.sub(r"[^a-z0-9]+", "_", event).strip("_") or "warning"
    return f"weather_warning_{suffix}"[:96]


class HorizonGlobalAlertNormalizer:
    ENGINE_VERSION = "horizon-global-alert-normalizer-v0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source_for_observation(self, observation: HorizonRawObservation) -> HorizonSource:
        return self.db.query(HorizonSource).filter(HorizonSource.id == observation.source_id).one()

    def normalize_gdacs_observation(self, observation_id: int) -> dict:
        observation = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == observation_id
        ).one_or_none()
        if observation is None:
            raise ValueError("GDACS raw observation not found")
        source = self._source_for_observation(observation)
        if source.source_key != "gdacs-official" or source.source_class != "official_multilateral":
            raise ValueError("observation is not from the approved GDACS multilateral source")
        if observation.observation_type != "multilateral_disaster_alert_snapshot":
            raise ValueError("observation is not a GDACS disaster alert snapshot")
        facts = observation.canonical_facts or {}
        event_type = str(facts.get("normalized_event_type_hint") or "global_disaster")[:96]
        candidate = HorizonSourceService(self.db).build_candidate(
            HorizonCandidateBuild(
                observation_ids=[observation.id],
                event_type=event_type,
                title=observation.title,
                geography=list(observation.geography or []),
                normalized_facts={
                    "provider": "GDACS",
                    "canonical_event_id": facts.get("canonical_event_id"),
                    "event_code": facts.get("event_code"),
                    "event_id": facts.get("event_id"),
                    "episode_id": facts.get("episode_id"),
                    "alert_level": facts.get("alert_level"),
                    "provider_updated_at": facts.get("provider_updated_at"),
                    "geography_status": "provider_supplied" if observation.geography else "unknown",
                    "source_observation_id": observation.id,
                    "adapter_promoted_fact": False,
                },
                normalizer_version=self.ENGINE_VERSION,
            )
        )
        readiness = HorizonSourceService(self.db).promotion_readiness(candidate)
        return {
            "observation_id": observation.id,
            "candidate_id": candidate.id,
            "candidate_key": candidate.candidate_key,
            "event_type": candidate.event_type,
            "promotion_status": candidate.promotion_status,
            "promoted_event_id": candidate.promoted_event_id,
            "promotion_readiness": readiness,
            "critical_semantics": {
                "normalizer_promoted_event": False,
                "single_gdacs_snapshot_is_automatic_confirmed_fact": False,
                "alert_level_is_probability": False,
            },
        }

    def normalize_meteoalarm_observation(self, observation_id: int) -> dict:
        observation = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id == observation_id
        ).one_or_none()
        if observation is None:
            raise ValueError("MeteoAlarm raw observation not found")
        source = self._source_for_observation(observation)
        if not source.source_key.startswith("meteoalarm:") or source.source_class != "official_aggregator":
            raise ValueError("observation is not from an approved MeteoAlarm aggregator source")
        if observation.observation_type != "official_weather_warning_aggregated_snapshot":
            raise ValueError("observation is not a MeteoAlarm weather-warning snapshot")
        facts = observation.canonical_facts or {}
        event_type = _meteoalarm_event_type(facts, observation.title)
        candidate = HorizonSourceService(self.db).build_candidate(
            HorizonCandidateBuild(
                observation_ids=[observation.id],
                event_type=event_type,
                title=observation.title,
                geography=list(observation.geography or []),
                normalized_facts={
                    "provider": "MeteoAlarm",
                    "country_slug": facts.get("country_slug"),
                    "country_iso2": facts.get("country_iso2"),
                    "canonical_warning_id": facts.get("canonical_warning_id"),
                    "event": facts.get("event"),
                    "severity": facts.get("severity"),
                    "urgency": facts.get("urgency"),
                    "certainty": facts.get("certainty"),
                    "area": facts.get("area"),
                    "effective_at": facts.get("effective_at"),
                    "expires_at": facts.get("expires_at"),
                    "provider_updated_at": facts.get("provider_updated_at"),
                    "geography_status": "country_known",
                    "source_observation_id": observation.id,
                    "aggregated_national_origin": True,
                    "adapter_promoted_fact": False,
                },
                normalizer_version=self.ENGINE_VERSION,
            )
        )
        readiness = HorizonSourceService(self.db).promotion_readiness(candidate)
        return {
            "observation_id": observation.id,
            "candidate_id": candidate.id,
            "candidate_key": candidate.candidate_key,
            "event_type": candidate.event_type,
            "promotion_status": candidate.promotion_status,
            "promoted_event_id": candidate.promoted_event_id,
            "promotion_readiness": readiness,
            "critical_semantics": {
                "normalizer_promoted_event": False,
                "single_meteoalarm_snapshot_is_automatic_confirmed_fact": False,
                "aggregator_may_relay_national_source": True,
                "severity_is_probability": False,
            },
        }

    @staticmethod
    def _latest_observations(rows: list[HorizonRawObservation], fact_key: str, *, limit: int) -> list[HorizonRawObservation]:
        result: list[HorizonRawObservation] = []
        seen: set[str] = set()
        for row in rows:
            facts = row.canonical_facts or {}
            identity = str(facts.get(fact_key) or row.external_key)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(row)
            if len(result) >= limit:
                break
        return result

    def normalize_latest_gdacs(self, *, max_observations: int = 500) -> dict:
        source = self.db.query(HorizonSource).filter(HorizonSource.source_key == "gdacs-official").one_or_none()
        if source is None:
            return {"source_key": "gdacs-official", "normalized": 0, "candidates": [], "skipped": True}
        rows = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.observation_type == "multilateral_disaster_alert_snapshot",
        ).order_by(
            HorizonRawObservation.published_at.desc(),
            HorizonRawObservation.observed_at.desc(),
            HorizonRawObservation.id.desc(),
        ).limit(max_observations * 4).all()
        selected = self._latest_observations(rows, "canonical_event_id", limit=max_observations)
        candidates = [self.normalize_gdacs_observation(row.id) for row in selected]
        return {
            "source_key": source.source_key,
            "observations_scanned": len(rows),
            "latest_canonical_observations": len(selected),
            "normalized": len(candidates),
            "candidates": candidates,
            "events_promoted": 0,
        }

    def normalize_latest_meteoalarm(self, *, max_observations: int = 500) -> dict:
        sources = self.db.query(HorizonSource).filter(
            HorizonSource.source_key.like("meteoalarm:%")
        ).all()
        source_ids = [source.id for source in sources]
        if not source_ids:
            return {"source_prefix": "meteoalarm:", "normalized": 0, "candidates": [], "skipped": True}
        rows = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id.in_(source_ids),
            HorizonRawObservation.observation_type == "official_weather_warning_aggregated_snapshot",
        ).order_by(
            HorizonRawObservation.published_at.desc(),
            HorizonRawObservation.observed_at.desc(),
            HorizonRawObservation.id.desc(),
        ).limit(max_observations * 4).all()
        selected: list[HorizonRawObservation] = []
        seen: set[str] = set()
        for row in rows:
            facts = row.canonical_facts or {}
            identity = f"{facts.get('country_slug')}:{facts.get('canonical_warning_id') or row.external_key}"
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(row)
            if len(selected) >= max_observations:
                break
        candidates = [self.normalize_meteoalarm_observation(row.id) for row in selected]
        return {
            "source_prefix": "meteoalarm:",
            "observations_scanned": len(rows),
            "latest_canonical_observations": len(selected),
            "normalized": len(candidates),
            "candidates": candidates,
            "events_promoted": 0,
        }
