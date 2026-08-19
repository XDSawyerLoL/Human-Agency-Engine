from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..horizon_convergence_models import HorizonConvergenceSnapshot
from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_weather_chain_models import HorizonWeatherImpactChain
from .policy import sha256_dict


ROLE_ORDER = (
    "precursor",
    "confirmation",
    "physical_state",
    "behavioral_outcome",
    "operational_impact",
    "materialization",
    "context",
)

SIGNAL_ROLE_MAP = {
    "media_attention": {"precursor", "context"},
    "heat_attention": {"precursor", "context"},
    "weather_model_consensus": {"precursor"},
    "search_interest": {"precursor", "behavioral_outcome"},
    "cooling_search_interest": {"precursor", "behavioral_outcome"},
    "scarcity_search": {"precursor", "behavioral_outcome"},
    "scarcity_mentions": {"precursor", "context"},
    "queue_reports": {"behavioral_outcome"},
    "purchase_velocity": {"behavioral_outcome"},
    "retail_demand": {"behavioral_outcome"},
    "precautionary_buying": {"behavioral_outcome"},
    "queue_density": {"behavioral_outcome", "physical_state"},
    "inventory_pressure": {"physical_state", "behavioral_outcome"},
    "stock_availability": {"physical_state"},
    "shortage_reports": {"materialization", "physical_state"},
    "stockout_reports": {"materialization", "physical_state"},
    "cooling_load_pressure_live": {"behavioral_outcome"},
    "cooling_load_pressure": {"behavioral_outcome", "materialization"},
    "fuel_stock_pressure": {"physical_state", "materialization"},
}

SOURCE_FALLBACK_ROLES = {
    "model_forecast": {"precursor"},
    "news_global": {"precursor", "context"},
    "social_weak_signal": {"precursor", "context"},
    "behavioral_signal": {"behavioral_outcome"},
    "official_primary": {"confirmation", "physical_state"},
    "official_statistical": {"physical_state"},
    "official_multilateral": {"precursor", "confirmation", "physical_state"},
    "official_aggregator": {"confirmation", "physical_state"},
}

CAPABILITY_MATRIX = (
    {"source_key": "windy-point-forecast", "role": "weather multi-model precursor", "status": "implemented_requires_key", "evidence_roles": ["precursor"], "historical_backtest_safe": False, "reason": "current Point Forecast API exposes latest forecasts, not historical forecast snapshots"},
    {"source_key": "meteofrance-vigilance", "role": "official weather confirmation", "status": "implemented_requires_key", "evidence_roles": ["confirmation", "physical_state"], "historical_backtest_safe": True},
    {"source_key": "meteoalarm-atom", "role": "European official-warning aggregation", "status": "implemented_open_data", "evidence_roles": ["confirmation", "physical_state"], "historical_backtest_safe": False, "reason": "public Atom feeds are live distribution; direct archived EDR queries require access token"},
    {"source_key": "meteoalarm-edr", "role": "European realtime and archived official warnings", "status": "gated_external_access", "evidence_roles": ["confirmation", "physical_state"], "historical_backtest_safe": True, "reason": "MeteoAlarm EDR location queries and MQTT require a registered token"},
    {"source_key": "gdacs-official", "role": "global multilateral disaster detection and corroboration", "status": "implemented_open_data", "evidence_roles": ["precursor", "confirmation", "physical_state"], "historical_backtest_safe": True, "reason": "GDACS search API supports custom historical extraction; imported provider timestamps must remain point-in-time"},
    {"source_key": "rte-eco2mix-regional-tr", "role": "near-live regional collective load", "status": "implemented_open_data", "evidence_roles": ["behavioral_outcome", "physical_state"], "historical_backtest_safe": False, "reason": "realtime telemetry/estimates are not final labels"},
    {"source_key": "rte-eco2mix-regional-cons-def", "role": "consolidated/final regional load truth stream", "status": "implemented_open_data", "evidence_roles": ["behavioral_outcome", "materialization"], "historical_backtest_safe": True},
    {"source_key": "vigicrues-official", "role": "official river-flood vigilance and physical state", "status": "implemented_open_data", "evidence_roles": ["confirmation", "physical_state"], "historical_backtest_safe": False, "reason": "live feed alone is not a historical archive"},
    {"source_key": "sncf-service-alerts", "role": "official rail operational disruption", "status": "implemented_open_data", "evidence_roles": ["confirmation", "operational_impact"], "historical_backtest_safe": False, "reason": "live incident feed alone is not a point-in-time historical archive"},
    {"source_key": "gdelt-doc-2", "role": "broad media/world-event discovery", "status": "implemented_open_data", "evidence_roles": ["precursor", "context"], "historical_backtest_safe": True},
    {"source_key": "fr-fuel-ruptures-live", "role": "official station-level supply state", "status": "implemented_open_data", "evidence_roles": ["confirmation", "physical_state", "materialization"], "historical_backtest_safe": False},
    {"source_key": "google-trends-alpha", "role": "search behavior / collective attention", "status": "gated_external_access", "evidence_roles": ["precursor", "behavioral_outcome"], "historical_backtest_safe": True, "reason": "official Google Trends API remains restricted alpha access"},
    {"source_key": "airparif-realtime", "role": "environmental physical-state context for Ile-de-France", "status": "gated_requires_provider_key", "evidence_roles": ["physical_state", "context"], "historical_backtest_safe": True, "reason": "API access requires an Airparif key"},
)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _source_roles(source: HorizonSource) -> set[str]:
    metadata = source.metadata_json or {}
    explicit = metadata.get("evidence_roles")
    if isinstance(explicit, list):
        roles = {str(item) for item in explicit if str(item) in ROLE_ORDER}
        if roles:
            return roles
    return set(SOURCE_FALLBACK_ROLES.get(source.source_class, {"context"}))


def _unregistered_event_roles(source_key: str) -> set[str]:
    key = source_key.lower()
    if any(item in key for item in ("meteofrance", "meteoalarm", "vigicrues", "sncf", "fuel")):
        return {"confirmation", "physical_state"}
    if "gdacs" in key:
        return {"precursor", "confirmation", "physical_state"}
    if "rte" in key:
        return {"physical_state"}
    if "gdelt" in key or "media" in key:
        return {"precursor", "context"}
    if "windy" in key:
        return {"precursor"}
    return {"context"}


def _independence_family(source_key: str, source: HorizonSource | None) -> str:
    if source is not None:
        metadata = source.metadata_json or {}
        explicit = str(metadata.get("independence_family") or "").strip()
        if explicit:
            return explicit
    normalized = source_key.lower().strip()
    if normalized in {"meteofrance-vigilance", "meteofrance-vigilance-archive"}:
        return "weather-warning:france"
    if normalized.startswith("meteoalarm:"):
        return f"weather-warning:{normalized.split(':', 1)[1]}"
    return source_key


class HorizonConvergenceService:
    ENGINE_VERSION = "horizon-evidence-convergence-v0.3"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def capability_matrix() -> dict:
        return {
            "engine": HorizonConvergenceService.ENGINE_VERSION,
            "capabilities": list(CAPABILITY_MATRIX),
            "critical_semantics": {
                "more_sources_do_not_automatically_mean_more_truth": True,
                "independence_and_role_diversity_matter": True,
                "relay_or_aggregator_sources_can_share_independence_family": True,
                "convergence_score_is_probability": False,
                "gated_sources_are_not_claimed_as_connected": True,
            },
        }

    def _event_tree(self, event: HorizonGlobalEvent, as_of: datetime) -> list[HorizonGlobalEvent]:
        result: dict[int, HorizonGlobalEvent] = {event.id: event}
        pending = [event]
        while pending:
            current = pending.pop()
            member_ids = (current.raw_facts or {}).get("member_event_ids") or []
            clean_ids: list[int] = []
            for value in member_ids:
                try:
                    clean_ids.append(int(value))
                except (TypeError, ValueError):
                    pass
            if not clean_ids:
                continue
            rows = self.db.query(HorizonGlobalEvent).filter(
                HorizonGlobalEvent.id.in_(clean_ids),
                HorizonGlobalEvent.first_observed_at <= as_of,
            ).all()
            for row in rows:
                if row.id not in result:
                    result[row.id] = row
                    pending.append(row)
        return sorted(result.values(), key=lambda item: (item.first_observed_at, item.id))

    @staticmethod
    def _observation_ids(events: list[HorizonGlobalEvent]) -> set[int]:
        result: set[int] = set()
        for event in events:
            facts = event.raw_facts or {}
            for value in facts.get("observation_ids") or []:
                try:
                    result.add(int(value))
                except (TypeError, ValueError):
                    pass
            normalized = facts.get("normalized_facts") or {}
            if isinstance(normalized, dict):
                value = normalized.get("source_observation_id")
                try:
                    if value is not None:
                        result.add(int(value))
                except (TypeError, ValueError):
                    pass
        return result

    def build_snapshot(self, event_id: int, *, as_of: datetime | None = None) -> dict:
        event = self.db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == event_id).one_or_none()
        if event is None:
            raise ValueError("HORIZON event not found")
        requested_cutoff = _utc_naive(as_of or datetime.utcnow())
        if event.first_observed_at > requested_cutoff:
            raise ValueError("event was not yet known at requested convergence cutoff")

        events = self._event_tree(event, requested_cutoff)
        event_ids = [item.id for item in events]
        observation_ids = self._observation_ids(events)
        observations = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id.in_(observation_ids),
            HorizonRawObservation.observed_at <= requested_cutoff,
        ).all() if observation_ids else []

        source_ids = {item.source_id for item in observations}
        registered_sources = self.db.query(HorizonSource).filter(
            HorizonSource.id.in_(source_ids)
        ).all() if source_ids else []
        sources_by_id = {item.id: item for item in registered_sources}

        signals = self.db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id.in_(event_ids),
            HorizonSocialSignal.observed_at <= requested_cutoff,
        ).order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc()).all()
        signal_source_keys = {str(item.source) for item in signals if str(item.source).strip()}
        signal_sources = self.db.query(HorizonSource).filter(
            HorizonSource.source_key.in_(signal_source_keys)
        ).all() if signal_source_keys else []
        signal_source_by_key = {item.source_key: item for item in signal_sources}

        event_source_keys = {str(item.source) for item in events if str(item.source).strip()}
        event_sources = self.db.query(HorizonSource).filter(
            HorizonSource.source_key.in_(event_source_keys)
        ).all() if event_source_keys else []
        event_source_by_key = {item.source_key: item for item in event_sources}

        chains = self.db.query(HorizonWeatherImpactChain).filter(
            HorizonWeatherImpactChain.created_at <= requested_cutoff,
        ).all()
        related_chains = [item for item in chains if item.confirmed_event_id in event_ids or item.regional_event_id in event_ids]

        source_keys: set[str] = set()
        source_classes: set[str] = set()
        roles: set[str] = set()
        family_members: dict[str, set[str]] = defaultdict(set)
        trust_by_family: dict[str, float] = {}
        knowledge_times = [item.first_observed_at for item in events]

        def register_source(source_key: str, source: HorizonSource | None, trust: float) -> str:
            family = _independence_family(source_key, source)
            source_keys.add(source_key)
            family_members[family].add(source_key)
            trust_by_family[family] = max(trust_by_family.get(family, 0.0), float(trust))
            if source is not None:
                source_classes.add(source.source_class)
            return family

        event_evidence = []
        for item in events:
            source_key = str(item.source)
            source = event_source_by_key.get(source_key)
            source_roles = _source_roles(source) if source is not None else _unregistered_event_roles(source_key)
            family = register_source(source_key, source, float(source.trust_weight) if source is not None else float(item.source_reliability))
            roles.update(source_roles)
            event_evidence.append({
                "event_id": item.id,
                "event_type": item.event_type,
                "source_key": source_key,
                "independence_family": family,
                "roles": sorted(source_roles),
                "first_observed_at": item.first_observed_at.isoformat(),
            })

        observation_evidence = []
        for observation in sorted(observations, key=lambda item: (item.observed_at, item.id)):
            source = sources_by_id.get(observation.source_id)
            if source is None:
                continue
            source_roles = _source_roles(source)
            family = register_source(source.source_key, source, float(source.trust_weight))
            roles.update(source_roles)
            knowledge_times.append(observation.observed_at)
            observation_evidence.append({
                "observation_id": observation.id,
                "source_key": source.source_key,
                "source_class": source.source_class,
                "independence_family": family,
                "roles": sorted(source_roles),
                "observation_type": observation.observation_type,
                "observed_at": observation.observed_at.isoformat(),
            })

        signal_evidence = []
        for signal in signals:
            source_key = str(signal.source)
            source = signal_source_by_key.get(source_key)
            family = register_source(
                source_key,
                source,
                float(source.trust_weight) if source is not None else float(signal.reliability),
            )
            if source is not None:
                roles.update(_source_roles(source))
            signal_roles = set(SIGNAL_ROLE_MAP.get(signal.signal_type, {"context"}))
            roles.update(signal_roles)
            knowledge_times.append(signal.observed_at)
            signal_evidence.append({
                "signal_id": signal.id,
                "event_id": signal.event_id,
                "source_key": source_key,
                "independence_family": family,
                "signal_type": signal.signal_type,
                "roles": sorted(signal_roles),
                "reliability": float(signal.reliability),
                "normalized_score": float(signal.normalized_score),
                "observed_at": signal.observed_at.isoformat(),
            })

        if related_chains:
            roles.update({"confirmation", "behavioral_outcome", "materialization"})
            knowledge_times.extend(item.created_at for item in related_chains)

        independence_families = sorted(family_members)
        independent_sources = len(independence_families)
        mean_trust = sum(trust_by_family.values()) / len(trust_by_family) if trust_by_family else 0.0
        source_diversity = min(independent_sources / 5.0, 1.0)
        role_diversity = min(len(roles) / 5.0, 1.0)
        class_diversity = min(len(source_classes) / 4.0, 1.0)
        convergence_score = round(min(1.0, 0.30 * role_diversity + 0.25 * source_diversity + 0.20 * class_diversity + 0.25 * mean_trust), 4)
        knowledge_as_of = max(knowledge_times) if knowledge_times else event.first_observed_at

        evidence_snapshot = {
            "event_ids": event_ids,
            "event_evidence": event_evidence,
            "observation_evidence": observation_evidence,
            "signal_evidence": signal_evidence,
            "weather_chain_ids": [item.id for item in related_chains],
            "source_keys": sorted(source_keys),
            "provider_source_count": len(source_keys),
            "independence_families": independence_families,
            "family_members": {key: sorted(value) for key, value in sorted(family_members.items())},
            "source_classes": sorted(source_classes),
            "independence_family_trust": {key: round(value, 4) for key, value in sorted(trust_by_family.items())},
            "evidence_roles": [role for role in ROLE_ORDER if role in roles],
            "mean_unique_independence_family_trust": round(mean_trust, 4),
            "role_coverage": {role: role in roles for role in ROLE_ORDER},
            "knowledge_as_of": knowledge_as_of.isoformat(),
            "diagnostic_formula": {
                "role_diversity_weight": 0.30,
                "independence_family_diversity_weight": 0.25,
                "source_class_diversity_weight": 0.20,
                "mean_unique_independence_family_trust_weight": 0.25,
            },
            "critical_semantics": {
                "convergence_score_is_probability": False,
                "repeated_rows_from_same_source_do_not_create_source_independence": True,
                "aggregator_and_origin_can_share_independence_family": True,
                "source_trust_counted_once_per_independence_family": True,
                "official_confirmation_remains_distinct_from_behavior": True,
                "materialization_remains_distinct_from_precursor": True,
                "evidence_after_cutoff_excluded": True,
            },
        }
        snapshot_key = sha256_dict({"engine": self.ENGINE_VERSION, "event_id": event.id, "evidence": evidence_snapshot})
        existing = self.db.query(HorizonConvergenceSnapshot).filter(HorizonConvergenceSnapshot.snapshot_key == snapshot_key).one_or_none()
        if existing is None:
            row = HorizonConvergenceSnapshot(
                snapshot_key=snapshot_key,
                event_id=event.id,
                engine_version=self.ENGINE_VERSION,
                as_of=knowledge_as_of,
                independent_sources=independent_sources,
                source_classes=sorted(source_classes),
                evidence_roles=[role for role in ROLE_ORDER if role in roles],
                convergence_score=convergence_score,
                evidence_snapshot=evidence_snapshot,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            replayed = False
        else:
            row = existing
            replayed = True
        result = self._serialize(row, replayed=replayed)
        result["requested_cutoff"] = requested_cutoff.isoformat()
        return result

    @staticmethod
    def _serialize(row: HorizonConvergenceSnapshot, *, replayed: bool = False) -> dict:
        return {
            "id": row.id,
            "snapshot_key": row.snapshot_key,
            "event_id": row.event_id,
            "engine_version": row.engine_version,
            "as_of": row.as_of.isoformat(),
            "independent_sources": row.independent_sources,
            "source_classes": row.source_classes,
            "evidence_roles": row.evidence_roles,
            "convergence_score": row.convergence_score,
            "convergence_score_is_probability": False,
            "evidence_snapshot": row.evidence_snapshot,
            "created_at": row.created_at.isoformat(),
            "replayed_existing_snapshot": replayed,
        }

    def list_snapshots(self, event_id: int, *, limit: int = 100) -> list[dict]:
        rows = self.db.query(HorizonConvergenceSnapshot).filter(
            HorizonConvergenceSnapshot.event_id == event_id
        ).order_by(HorizonConvergenceSnapshot.as_of.desc(), HorizonConvergenceSnapshot.id.desc()).limit(limit).all()
        return [self._serialize(row) for row in rows]
