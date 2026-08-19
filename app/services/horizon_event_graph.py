from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy.orm import Session

from ..horizon_event_graph_models import HorizonEventGraphSnapshot
from ..horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from ..horizon_weather_chain_models import HorizonWeatherImpactChain
from .horizon_heat_regions import DEPARTMENT_TO_REGION
from .policy import sha256_dict


COUNTRY_ALIASES = {
    "FR": "FR", "FRA": "FR", "FRANCE": "FR",
    "BE": "BE", "BEL": "BE", "BELGIUM": "BE",
    "DE": "DE", "DEU": "DE", "GERMANY": "DE",
    "ES": "ES", "ESP": "ES", "SPAIN": "ES",
    "IT": "IT", "ITA": "IT", "ITALY": "IT",
    "PT": "PT", "PRT": "PT", "PORTUGAL": "PT",
    "GB": "GB", "GBR": "GB", "UNITED KINGDOM": "GB", "UK": "GB",
    "IE": "IE", "IRL": "IE", "IRELAND": "IE",
    "CH": "CH", "CHE": "CH", "SWITZERLAND": "CH",
    "NL": "NL", "NLD": "NL", "NETHERLANDS": "NL",
    "LU": "LU", "LUX": "LU", "LUXEMBOURG": "LU",
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "dans", "pour", "avec", "sur", "une", "des",
    "de", "du", "la", "le", "les", "un", "warning", "alert", "alerte", "vigilance",
    "official", "officiel", "synthetic", "synthétique", "region", "région",
}

FAMILY_MAP = {
    "extreme_heat": "heat",
    "extreme_heat_region": "heat",
    "extreme_cold": "snow_cold",
    "snow_ice": "snow_cold",
    "strong_wind": "storm",
    "thunderstorm": "storm",
    "tropical_cyclone": "storm",
    "heavy_rain": "hydro",
    "flood": "hydro",
    "river_flood_risk": "hydro",
    "wildfire": "wildfire",
    "earthquake": "seismic",
    "volcano": "volcanic",
    "drought": "drought",
    "rail_transport_disruption": "transport",
    "supply_disruption": "supply",
    "fuel_supply_disruption": "supply",
}

DEPENDENCY_RULES = {
    ("hydro", "transport"): 0.95,
    ("storm", "transport"): 0.90,
    ("snow_cold", "transport"): 0.90,
    ("wildfire", "transport"): 0.85,
    ("seismic", "transport"): 0.90,
    ("hydro", "supply"): 0.80,
    ("storm", "supply"): 0.75,
    ("wildfire", "supply"): 0.80,
    ("seismic", "supply"): 0.85,
}


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc_naive(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_naive(parsed)


def _family(event_type: str) -> str:
    if event_type in FAMILY_MAP:
        return FAMILY_MAP[event_type]
    if event_type.startswith("weather_warning_"):
        text = event_type.lower()
        if "heat" in text or "temperature" in text:
            return "heat"
        if "rain" in text or "flood" in text:
            return "hydro"
        if "wind" in text or "storm" in text:
            return "storm"
        if "snow" in text or "ice" in text or "cold" in text:
            return "snow_cold"
        return "weather"
    return event_type


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", text.lower())
    return {word for word in words if word not in STOPWORDS}


def _semantic_similarity(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _source_family(source_key: str, source: HorizonSource | None) -> str:
    if source is not None:
        explicit = str((source.metadata_json or {}).get("independence_family") or "").strip()
        if explicit:
            return explicit
    key = source_key.lower().strip()
    if key in {"meteofrance-vigilance", "meteofrance-vigilance-archive"}:
        return "weather-warning:france"
    if key.startswith("meteoalarm:"):
        return f"weather-warning:{key.split(':', 1)[1]}"
    return source_key


def _geo_profile(values: list[str], facts: dict | None = None) -> dict:
    facts = facts or {}
    countries: set[str] = set()
    locals_: set[str] = set()
    region_tokens: set[str] = set()

    raw_values = [str(item).strip() for item in values if str(item).strip()]
    for extra in (
        facts.get("country_iso2"), facts.get("country"), facts.get("domain_id"),
        facts.get("region_code"), facts.get("segment_code"),
    ):
        if extra:
            raw_values.append(str(extra).strip())
    departments = facts.get("departments") or []
    if isinstance(departments, list):
        raw_values.extend(str(item).strip() for item in departments if str(item).strip())

    for raw in raw_values:
        upper = raw.upper()
        alias = COUNTRY_ALIASES.get(upper)
        if alias:
            countries.add(alias)
            continue
        if upper.startswith("REGION:"):
            code = upper.split(":", 1)[1]
            countries.add("FR")
            region_tokens.add(f"FR-REGION:{code}")
            locals_.add(upper)
            continue
        if upper.startswith("VIGICRUES:"):
            countries.add("FR")
            locals_.add(upper)
            continue
        if upper in DEPARTMENT_TO_REGION:
            countries.add("FR")
            locals_.add(f"FR-DEPT:{upper}")
            region_tokens.add(f"FR-REGION:{DEPARTMENT_TO_REGION[upper]}")
            continue
        if len(upper) == 2 and upper.isalpha():
            countries.add(upper)
        elif upper:
            locals_.add(upper)
    return {
        "countries": sorted(countries),
        "local_tokens": sorted(locals_),
        "region_tokens": sorted(region_tokens),
    }


def _geo_score(left: dict, right: dict) -> tuple[float, str]:
    left_local = set(left["local_tokens"])
    right_local = set(right["local_tokens"])
    if left_local & right_local:
        return 1.0, "exact_local_overlap"
    left_regions = set(left["region_tokens"])
    right_regions = set(right["region_tokens"])
    if left_regions & right_regions:
        return 0.90, "same_normalized_region"
    left_countries = set(left["countries"])
    right_countries = set(right["countries"])
    if left_countries & right_countries:
        return 0.55, "same_country_only"
    return 0.0, "no_geographic_overlap"


def _temporal_distance_hours(left: dict, right: dict) -> float:
    if left["valid_from"] <= right["valid_to"] and right["valid_from"] <= left["valid_to"]:
        return 0.0
    if left["valid_to"] < right["valid_from"]:
        return (right["valid_from"] - left["valid_to"]).total_seconds() / 3600.0
    return (left["valid_from"] - right["valid_to"]).total_seconds() / 3600.0


def _temporal_score(left: dict, right: dict) -> tuple[float, float]:
    distance = max(0.0, _temporal_distance_hours(left, right))
    if distance == 0:
        return 1.0, 0.0
    if distance <= 6:
        return 0.90, distance
    if distance <= 24:
        return 0.75, distance
    if distance <= 72:
        return 0.50, distance
    if distance <= 168:
        return 0.25, distance
    return 0.0, distance


class _DisjointSet:
    def __init__(self, keys: list[str]):
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != key:
            nxt = self.parent[key]
            self.parent[key] = root
            key = nxt
        return root

    def union(self, left: str, right: str) -> None:
        a = self.find(left)
        b = self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


class HorizonEventGraphService:
    ENGINE_VERSION = "horizon-event-graph-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _event_window(event: HorizonGlobalEvent) -> tuple[datetime, datetime]:
        facts = event.raw_facts or {}
        normalized = facts.get("normalized_facts") or {}
        period = normalized.get("period") if isinstance(normalized, dict) else {}
        if not isinstance(period, dict):
            period = {}
        start = (
            _parse_datetime(facts.get("episode_start"))
            or _parse_datetime(period.get("begin_validity_time"))
            or _parse_datetime(normalized.get("effective_at") if isinstance(normalized, dict) else None)
            or _utc_naive(event.occurred_at)
            or _utc_naive(event.first_observed_at)
        )
        end = (
            _parse_datetime(facts.get("episode_end"))
            or _parse_datetime(period.get("end_validity_time"))
            or _parse_datetime(normalized.get("expires_at") if isinstance(normalized, dict) else None)
            or start + timedelta(hours=24)
        )
        if end < start:
            end = start
        return start, end

    @staticmethod
    def _candidate_window(candidate: HorizonEventCandidate) -> tuple[datetime, datetime]:
        facts = candidate.normalized_facts or {}
        target = facts.get("forecast_target_window") or {}
        if not isinstance(target, dict):
            target = {}
        start = (
            _parse_datetime(target.get("start"))
            or _parse_datetime(facts.get("effective_at"))
            or _parse_datetime(facts.get("provider_updated_at"))
            or _utc_naive(candidate.first_observed_at)
        )
        end = (
            _parse_datetime(target.get("end"))
            or _parse_datetime(facts.get("expires_at"))
            or _utc_naive(candidate.last_observed_at)
        )
        if end is None or end <= start:
            end = start + timedelta(hours=24)
        return start, end

    def _source_registry(self) -> tuple[dict[str, HorizonSource], dict[int, HorizonSource]]:
        sources = self.db.query(HorizonSource).all()
        return ({row.source_key: row for row in sources}, {row.id: row for row in sources})

    def _nodes(self, request: HorizonEventGraphBuildRequest, cutoff: datetime) -> tuple[list[dict], dict[str, object]]:
        start = cutoff - timedelta(hours=request.lookback_hours)
        source_by_key, source_by_id = self._source_registry()
        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.first_observed_at >= start,
                HorizonGlobalEvent.first_observed_at <= cutoff,
            )
            .order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .limit(request.max_events)
            .all()
        )
        candidates = (
            self.db.query(HorizonEventCandidate)
            .filter(
                HorizonEventCandidate.first_observed_at >= start,
                HorizonEventCandidate.first_observed_at <= cutoff,
            )
            .order_by(HorizonEventCandidate.first_observed_at.asc(), HorizonEventCandidate.id.asc())
            .limit(request.max_candidates)
            .all()
        )

        candidate_observation_ids: set[int] = set()
        for candidate in candidates:
            for value in candidate.corroborating_observation_ids or []:
                try:
                    candidate_observation_ids.add(int(value))
                except (TypeError, ValueError):
                    pass
        observations = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id.in_(candidate_observation_ids)
        ).all() if candidate_observation_ids else []
        observation_by_id = {row.id: row for row in observations}

        nodes: list[dict] = []
        node_objects: dict[str, object] = {}
        event_node_keys: dict[int, str] = {}
        candidate_node_keys: dict[int, str] = {}

        for event in events:
            start_at, end_at = self._event_window(event)
            source = source_by_key.get(event.source)
            family = _source_family(event.source, source)
            raw = event.raw_facts or {}
            normalized = raw.get("normalized_facts") or {}
            geo_facts = dict(raw)
            if isinstance(normalized, dict):
                geo_facts.update(normalized)
            key = f"event:{event.id}"
            node = {
                "key": key,
                "node_type": "event",
                "ref_id": event.id,
                "event_type": event.event_type,
                "event_family": _family(event.event_type),
                "title": event.title,
                "status": event.status,
                "fact_status": "confirmed_or_derived_event",
                "knowledge_at": _utc_naive(event.first_observed_at).isoformat(),
                "valid_from": start_at,
                "valid_to": end_at,
                "geography": _geo_profile(event.geography or [], geo_facts),
                "source_keys": [event.source],
                "independence_families": [family],
            }
            nodes.append(node)
            node_objects[key] = event
            event_node_keys[event.id] = key

        for candidate in candidates:
            start_at, end_at = self._candidate_window(candidate)
            source_keys: set[str] = set()
            families: set[str] = set()
            for value in candidate.corroborating_observation_ids or []:
                try:
                    observation = observation_by_id.get(int(value))
                except (TypeError, ValueError):
                    observation = None
                if observation is None:
                    continue
                source = source_by_id.get(observation.source_id)
                if source is None:
                    continue
                source_keys.add(source.source_key)
                families.add(_source_family(source.source_key, source))
            key = f"candidate:{candidate.id}"
            node = {
                "key": key,
                "node_type": "candidate",
                "ref_id": candidate.id,
                "event_type": candidate.event_type,
                "event_family": _family(candidate.event_type),
                "title": candidate.title,
                "status": candidate.promotion_status,
                "fact_status": "unconfirmed_candidate" if candidate.promoted_event_id is None else "candidate_promoted",
                "knowledge_at": _utc_naive(candidate.first_observed_at).isoformat(),
                "valid_from": start_at,
                "valid_to": end_at,
                "geography": _geo_profile(candidate.geography or [], candidate.normalized_facts or {}),
                "source_keys": sorted(source_keys),
                "independence_families": sorted(families),
                "promoted_event_id": candidate.promoted_event_id,
            }
            nodes.append(node)
            node_objects[key] = candidate
            candidate_node_keys[candidate.id] = key

        event_ids = list(event_node_keys)
        signals = (
            self.db.query(HorizonSocialSignal)
            .filter(
                HorizonSocialSignal.event_id.in_(event_ids),
                HorizonSocialSignal.observed_at <= cutoff,
            )
            .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
            .limit(request.max_signals)
            .all()
        ) if event_ids else []
        signal_node_keys: dict[int, str] = {}
        for signal in signals:
            source = source_by_key.get(signal.source)
            family = _source_family(signal.source, source)
            at = _utc_naive(signal.observed_at)
            key = f"signal:{signal.id}"
            node = {
                "key": key,
                "node_type": "signal",
                "ref_id": signal.id,
                "event_type": signal.signal_type,
                "event_family": "signal",
                "title": signal.signal_type,
                "status": "observed",
                "fact_status": "observed_signal",
                "knowledge_at": at.isoformat(),
                "valid_from": at,
                "valid_to": at,
                "geography": _geo_profile(signal.geography or []),
                "source_keys": [signal.source],
                "independence_families": [family],
                "parent_event_id": signal.event_id,
                "reliability": float(signal.reliability),
                "normalized_score": float(signal.normalized_score),
            }
            nodes.append(node)
            node_objects[key] = signal
            signal_node_keys[signal.id] = key

        return nodes, {
            "objects": node_objects,
            "event_keys": event_node_keys,
            "candidate_keys": candidate_node_keys,
            "signal_keys": signal_node_keys,
            "events": events,
            "candidates": candidates,
            "signals": signals,
        }

    @staticmethod
    def _public_node(node: dict) -> dict:
        return {
            key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in node.items()
        }

    @staticmethod
    def _same_episode_edge(left: dict, right: dict, threshold: float) -> dict | None:
        if left["node_type"] == "signal" or right["node_type"] == "signal":
            return None
        if left["event_family"] != right["event_family"]:
            return None
        geo, geo_basis = _geo_score(left["geography"], right["geography"])
        if geo <= 0:
            return None
        temporal, distance = _temporal_score(left, right)
        if temporal <= 0:
            return None
        exact_type = left["event_type"] == right["event_type"]
        type_score = 1.0 if exact_type else 0.85
        semantic = _semantic_similarity(left["title"], right["title"])
        score = round(0.40 * type_score + 0.30 * geo + 0.25 * temporal + 0.05 * semantic, 4)
        if score < threshold:
            return None
        if geo_basis == "same_country_only" and semantic < 0.08 and not exact_type:
            return None
        left_families = set(left["independence_families"])
        right_families = set(right["independence_families"])
        independent = not bool(left_families & right_families) if left_families and right_families else True
        return {
            "left": left["key"],
            "right": right["key"],
            "relation": "same_episode_support",
            "relation_class": "identity_support",
            "diagnostic_score": score,
            "diagnostic_score_is_probability": False,
            "independent_support": independent,
            "asserted_causality": False,
            "evidence": {
                "type_score": type_score,
                "same_event_family": left["event_family"],
                "geography_score": geo,
                "geography_basis": geo_basis,
                "temporal_score": temporal,
                "temporal_distance_hours": round(distance, 3),
                "semantic_similarity": round(semantic, 4),
            },
        }

    @staticmethod
    def _dependency_edge(left: dict, right: dict, threshold: float) -> dict | None:
        if left["node_type"] == "signal" or right["node_type"] == "signal":
            return None
        strength = DEPENDENCY_RULES.get((left["event_family"], right["event_family"]))
        if strength is None:
            return None
        left_known = _parse_datetime(left["knowledge_at"])
        right_known = _parse_datetime(right["knowledge_at"])
        if left_known is None or right_known is None or right_known <= left_known:
            return None
        geo, geo_basis = _geo_score(left["geography"], right["geography"])
        if geo < 0.55:
            return None
        delta = (right["valid_from"] - left["valid_from"]).total_seconds() / 3600.0
        if delta < -6 or delta > 120:
            return None
        temporal = 1.0 if 0 <= delta <= 24 else 0.75 if delta <= 72 else 0.55
        score = round(0.45 * geo + 0.35 * temporal + 0.20 * strength, 4)
        if score < threshold:
            return None
        return {
            "left": left["key"],
            "right": right["key"],
            "relation": "plausible_downstream_dependency",
            "relation_class": "hypothesis_dependency",
            "diagnostic_score": score,
            "diagnostic_score_is_probability": False,
            "independent_support": True,
            "asserted_causality": False,
            "evidence": {
                "mechanism_rule": f"{left['event_family']}->{right['event_family']}",
                "rule_strength": strength,
                "geography_score": geo,
                "geography_basis": geo_basis,
                "ordered_delta_hours": round(delta, 3),
                "causal_claim": False,
            },
        }

    def build(self, request: HorizonEventGraphBuildRequest) -> dict:
        cutoff = _utc_naive(request.as_of) if request.as_of else datetime.utcnow()
        nodes, context = self._nodes(request, cutoff)
        by_key = {node["key"]: node for node in nodes}
        edges: list[dict] = []
        edge_keys: set[str] = set()

        def add_edge(edge: dict) -> None:
            identity = sha256_dict({
                "left": edge["left"], "right": edge["right"], "relation": edge["relation"],
                "evidence": edge.get("evidence", {}),
            })
            if identity not in edge_keys:
                edge_keys.add(identity)
                edge["edge_key"] = identity
                edges.append(edge)

        event_keys: dict[int, str] = context["event_keys"]
        candidate_keys: dict[int, str] = context["candidate_keys"]
        signal_keys: dict[int, str] = context["signal_keys"]

        for candidate in context["candidates"]:
            if candidate.promoted_event_id in event_keys:
                add_edge({
                    "left": candidate_keys[candidate.id],
                    "right": event_keys[candidate.promoted_event_id],
                    "relation": "promoted_to_confirmed_event",
                    "relation_class": "explicit_evidence",
                    "diagnostic_score": 1.0,
                    "diagnostic_score_is_probability": False,
                    "independent_support": False,
                    "asserted_causality": False,
                    "evidence": {"database_relation": "candidate.promoted_event_id"},
                })

        for signal in context["signals"]:
            if signal.event_id in event_keys:
                add_edge({
                    "left": event_keys[signal.event_id],
                    "right": signal_keys[signal.id],
                    "relation": "observed_signal_attachment",
                    "relation_class": "observed_attachment",
                    "diagnostic_score": 1.0,
                    "diagnostic_score_is_probability": False,
                    "independent_support": True,
                    "asserted_causality": False,
                    "evidence": {
                        "database_relation": "signal.event_id",
                        "signal_type": signal.signal_type,
                        "signal_reliability": float(signal.reliability),
                    },
                })

        chains = self.db.query(HorizonWeatherImpactChain).filter(
            HorizonWeatherImpactChain.created_at <= cutoff
        ).all()
        for chain in chains:
            if chain.windy_candidate_id in candidate_keys and chain.confirmed_event_id in event_keys:
                add_edge({
                    "left": candidate_keys[chain.windy_candidate_id],
                    "right": event_keys[chain.confirmed_event_id],
                    "relation": "official_confirmation_of_precursor",
                    "relation_class": "explicit_evidence",
                    "diagnostic_score": 1.0,
                    "diagnostic_score_is_probability": False,
                    "independent_support": True,
                    "asserted_causality": False,
                    "evidence": {"weather_chain_id": chain.id, "lead_hours": chain.windy_to_official_lead_hours},
                })
            if chain.confirmed_event_id in event_keys and chain.regional_event_id in event_keys:
                add_edge({
                    "left": event_keys[chain.confirmed_event_id],
                    "right": event_keys[chain.regional_event_id],
                    "relation": "regional_episode_membership",
                    "relation_class": "explicit_evidence",
                    "diagnostic_score": 1.0,
                    "diagnostic_score_is_probability": False,
                    "independent_support": False,
                    "asserted_causality": False,
                    "evidence": {"weather_chain_id": chain.id},
                })
            if chain.regional_event_id in event_keys and chain.outcome_signal_id in signal_keys:
                add_edge({
                    "left": event_keys[chain.regional_event_id],
                    "right": signal_keys[chain.outcome_signal_id],
                    "relation": "observed_behavioral_proxy",
                    "relation_class": "observed_attachment",
                    "diagnostic_score": 1.0,
                    "diagnostic_score_is_probability": False,
                    "independent_support": True,
                    "asserted_causality": False,
                    "evidence": {"weather_chain_id": chain.id, "causal_proof": False},
                })

        episode_nodes = [node for node in nodes if node["node_type"] in {"event", "candidate"}]
        for index, left in enumerate(episode_nodes):
            for right in episode_nodes[index + 1:]:
                same = self._same_episode_edge(left, right, request.minimum_same_episode_score)
                if same is not None:
                    add_edge(same)
                dependency = self._dependency_edge(left, right, request.minimum_dependency_score)
                if dependency is not None:
                    add_edge(dependency)
                reverse = self._dependency_edge(right, left, request.minimum_dependency_score)
                if reverse is not None:
                    add_edge(reverse)

        dsu = _DisjointSet([node["key"] for node in nodes])
        cluster_relations = {
            "promoted_to_confirmed_event",
            "official_confirmation_of_precursor",
            "regional_episode_membership",
            "observed_signal_attachment",
            "observed_behavioral_proxy",
            "same_episode_support",
        }
        for edge in edges:
            if edge["relation"] in cluster_relations:
                dsu.union(edge["left"], edge["right"])

        components: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            components[dsu.find(node["key"])].append(node["key"])
        episodes = []
        for members in sorted(components.values(), key=lambda values: (min(values), len(values))):
            if len(members) < 2:
                continue
            member_nodes = [by_key[key] for key in members]
            episode_sources = sorted({source for node in member_nodes for source in node["source_keys"]})
            episode_families = sorted({family for node in member_nodes for family in node["independence_families"]})
            episode_key = sha256_dict({"engine": self.ENGINE_VERSION, "members": sorted(members)})
            episodes.append({
                "episode_key": episode_key,
                "member_keys": sorted(members),
                "node_count": len(members),
                "provider_sources": episode_sources,
                "independence_families": episode_families,
                "independent_origin_count": len(episode_families),
                "contains_unconfirmed_candidate": any(node["node_type"] == "candidate" and node["fact_status"] == "unconfirmed_candidate" for node in member_nodes),
                "episode_membership_is_probability": False,
            })

        public_nodes = [self._public_node(node) for node in nodes]
        public_edges = sorted(edges, key=lambda edge: (edge["left"], edge["right"], edge["relation"]))
        knowledge_times = [_parse_datetime(node["knowledge_at"]) for node in public_nodes]
        clean_knowledge = [value for value in knowledge_times if value is not None]
        knowledge_as_of = max(clean_knowledge) if clean_knowledge else cutoff
        window_start = min(clean_knowledge) if clean_knowledge else cutoff - timedelta(hours=request.lookback_hours)
        graph_snapshot = {
            "nodes": public_nodes,
            "edges": public_edges,
            "episodes": episodes,
            "thresholds": {
                "minimum_same_episode_score": request.minimum_same_episode_score,
                "minimum_dependency_score": request.minimum_dependency_score,
            },
            "relation_semantics": {
                "explicit_evidence": "relation already recorded by HORIZON data structures",
                "identity_support": "deterministic evidence that two nodes may describe the same real-world episode",
                "observed_attachment": "observed signal attached to an event; attachment is not causal proof",
                "hypothesis_dependency": "plausible downstream dependency only; never asserted causality",
            },
            "critical_semantics": {
                "same_episode_score_is_probability": False,
                "dependency_score_is_probability": False,
                "plausible_dependency_is_causal_proof": False,
                "weak_temporal_coincidence_creates_episode": False,
                "signals_are_not_reclassified_as_facts": True,
                "unconfirmed_candidates_remain_unconfirmed": True,
                "evidence_after_cutoff_excluded": True,
            },
        }
        graph_key = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "graph": graph_snapshot,
        })
        existing = self.db.query(HorizonEventGraphSnapshot).filter(
            HorizonEventGraphSnapshot.graph_key == graph_key
        ).one_or_none()
        if existing is None:
            row = HorizonEventGraphSnapshot(
                graph_key=graph_key,
                engine_version=self.ENGINE_VERSION,
                as_of=knowledge_as_of,
                window_start_at=window_start,
                node_count=len(public_nodes),
                edge_count=len(public_edges),
                episode_count=len(episodes),
                graph_snapshot=graph_snapshot,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            replayed = False
        else:
            row = existing
            replayed = True
        result = self._serialize(row, replayed=replayed)
        result["requested_cutoff"] = cutoff.isoformat()
        result["requested_lookback_hours"] = request.lookback_hours
        return result

    @staticmethod
    def _serialize(row: HorizonEventGraphSnapshot, *, replayed: bool = False) -> dict:
        return {
            "id": row.id,
            "graph_key": row.graph_key,
            "engine_version": row.engine_version,
            "as_of": row.as_of.isoformat(),
            "window_start_at": row.window_start_at.isoformat(),
            "node_count": row.node_count,
            "edge_count": row.edge_count,
            "episode_count": row.episode_count,
            "graph_snapshot": row.graph_snapshot,
            "created_at": row.created_at.isoformat(),
            "replayed_existing_snapshot": replayed,
        }

    def list_snapshots(self, *, limit: int = 50) -> list[dict]:
        rows = self.db.query(HorizonEventGraphSnapshot).order_by(
            HorizonEventGraphSnapshot.as_of.desc(), HorizonEventGraphSnapshot.id.desc()
        ).limit(limit).all()
        return [self._serialize(row) for row in rows]
