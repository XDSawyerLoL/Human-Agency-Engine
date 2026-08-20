from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import re

from sqlalchemy.orm import Session

from ..horizon_emerging_schemas import HorizonEmergingClusterRequest
from ..horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild
from .horizon_sources import HorizonSourceService


NORMALIZER_VERSION = "gdelt-emerging-cluster-v0.2-world"

CLASSIFICATION_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "supply": (
        ("supply_disruption", ("shortage", "shortages", "rationing", "supply disruption", "fuel shortage", "blockade", "pénurie", "penurie")),
    ),
    "weather_disaster": (
        ("extreme_heat", ("heatwave", "heat wave", "extreme heat", "canicule", "vague de chaleur")),
        ("wildfire", ("wildfire", "wild fire", "forest fire", "feu de forêt", "incendie de forêt")),
        ("flood", ("flooding", "flood", "flash flood", "inondation")),
        ("earthquake", ("earthquake", "seismic event", "séisme", "seisme")),
        ("tropical_cyclone", ("cyclone", "hurricane", "typhoon", "ouragan")),
        ("drought", ("drought", "sécheresse", "secheresse")),
    ),
    "conflict_security": (
        ("economic_sanctions", ("sanctions", "economic sanction", "trade sanction")),
        ("political_instability", ("coup", "state of emergency", "martial law")),
        ("geopolitical_conflict", ("military strike", "missile attack", "invasion", "armed conflict", "air strike")),
    ),
    "infrastructure": (
        ("rail_transport_disruption", ("rail strike", "train strike", "transport strike", "rail disruption")),
        ("internet_service_outage", ("internet outage", "network outage", "telecom outage")),
        ("power_grid_disruption", ("blackout", "power cut", "power outage", "grid outage")),
        ("critical_infrastructure_outage", ("infrastructure outage", "major outage", "service disruption")),
    ),
    "economy_labor": (
        ("mass_layoff", ("mass layoffs", "layoffs", "layoff", "job cuts", "redundancies")),
        ("industrial_closure", ("factory closure", "plant closure", "site closure")),
        ("corporate_distress", ("bankruptcy", "insolvency", "insolvent", "administration")),
    ),
    "public_health": (
        ("public_health_outbreak", ("disease outbreak", "outbreak", "epidemic", "pandemic", "public health emergency")),
    ),
    "regulation_policy": (
        ("trade_policy_change", ("export ban", "import ban", "tariff", "tariffs", "trade restriction", "trade restrictions")),
        ("regulatory_change", ("new regulation", "regulatory change", "new rules", "regulation takes effect")),
    ),
    "cyber_technology": (
        ("cyber_incident", ("cyber attack", "cyberattack", "ransomware", "data breach", "cyber incident")),
        ("technology_service_outage", ("cloud outage", "service outage", "platform outage", "data center outage")),
    ),
    "financial_stress": (
        ("financial_stress", ("bank run", "bank failure", "liquidity crisis", "credit crunch", "debt default", "market stress")),
    ),
    "energy_markets": (
        ("energy_supply_disruption", ("gas supply", "oil supply", "energy shortage", "power shortage")),
        ("energy_market_stress", ("energy crisis", "energy price spike", "gas price spike", "power price spike")),
    ),
}

EVENT_TITLES = {
    "supply_disruption": "Emerging supply-disruption episode",
    "extreme_heat": "Emerging extreme-heat episode",
    "wildfire": "Emerging wildfire episode",
    "flood": "Emerging flood episode",
    "earthquake": "Emerging earthquake episode",
    "tropical_cyclone": "Emerging tropical-cyclone episode",
    "drought": "Emerging drought episode",
    "economic_sanctions": "Emerging sanctions episode",
    "political_instability": "Emerging political-instability episode",
    "geopolitical_conflict": "Emerging geopolitical-conflict episode",
    "rail_transport_disruption": "Emerging rail-transport disruption episode",
    "internet_service_outage": "Emerging internet-service outage episode",
    "power_grid_disruption": "Emerging power-grid disruption episode",
    "critical_infrastructure_outage": "Emerging infrastructure-disruption episode",
    "mass_layoff": "Emerging mass-layoff episode",
    "industrial_closure": "Emerging industrial-closure episode",
    "corporate_distress": "Emerging corporate-distress episode",
    "public_health_outbreak": "Emerging public-health outbreak episode",
    "trade_policy_change": "Emerging trade-policy change episode",
    "regulatory_change": "Emerging regulatory-change episode",
    "cyber_incident": "Emerging cyber-incident episode",
    "technology_service_outage": "Emerging technology-service outage episode",
    "financial_stress": "Emerging financial-stress episode",
    "energy_supply_disruption": "Emerging energy-supply disruption episode",
    "energy_market_stress": "Emerging energy-market stress episode",
}

TOKEN_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "after", "over", "amid", "across", "new", "major",
    "de", "des", "du", "la", "le", "les", "une", "un", "dans", "avec", "pour", "sur", "apres", "après",
    "reports", "report", "reported", "raises", "concerns", "fears", "threatens", "expands", "intensifies",
    "announces", "announced", "another", "affect", "affects", "affected", "continue", "continues", "continued",
}
GENERIC_EPISODE_TOKENS = {
    # Event-category words explain *what kind* of story this is, but are too generic
    # to prove that two stories describe the same real-world episode.
    "shortage", "shortages", "supply", "disruption", "outage", "strike", "warning", "emergency", "crisis",
    "attack", "incident", "closure", "layoff", "layoffs", "regulation", "change", "market", "stress", "extreme",
    "heat", "heatwave", "flood", "flooding", "wildfire", "earthquake", "cyclone", "hurricane", "drought",
    # Newsroom/business boilerplate must never become an episode identity anchor.
    "mass", "unit", "units", "company", "companies", "group", "groups", "operation", "operations", "restructuring",
    "round", "jobs", "job", "cuts", "cut", "services", "service",
}
TOKEN_ALIASES = {
    "heatwave": "heat",
    "heatwaves": "heat",
    "trains": "rail",
    "train": "rail",
    "railway": "rail",
    "railways": "rail",
    "sanction": "sanctions",
}


def _bucket_start(value: datetime, minutes: int) -> datetime:
    minute = (value.minute // minutes) * minutes
    return value.replace(minute=minute, second=0, microsecond=0)


def _classify(observation: HorizonRawObservation) -> str | None:
    facts = observation.canonical_facts or {}
    family = str(facts.get("watch_family") or "")
    text = f"{observation.title} {observation.summary}".lower()
    for event_type, terms in CLASSIFICATION_RULES.get(family, ()):
        if any(term in text for term in terms):
            return event_type
    return None


def _episode_tokens(observation: HorizonRawObservation) -> set[str]:
    text = f"{observation.title} {observation.summary}".lower()
    raw = re.findall(r"[a-zA-ZÀ-ÿ0-9][a-zA-ZÀ-ÿ0-9._-]{2,}", text)
    tokens = {
        TOKEN_ALIASES.get(token, token)
        for token in raw
        if token not in TOKEN_STOPWORDS and token not in GENERIC_EPISODE_TOKENS
    }
    domain = str((observation.canonical_facts or {}).get("publisher_domain") or "").lower().split(":")[0]
    if domain:
        # Publisher identity is useful for audit but must not cause multiple stories
        # from one outlet to be treated as the same real-world episode.
        tokens.discard(domain)
    return tokens


def _episode_clusters(observations: list[HorizonRawObservation]) -> list[tuple[list[HorizonRawObservation], list[str]]]:
    if not observations:
        return []
    token_sets = [_episode_tokens(item) for item in observations]
    parent = list(range(len(observations)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for left in range(len(observations)):
        if not token_sets[left]:
            continue
        for right in range(left + 1, len(observations)):
            if token_sets[left] & token_sets[right]:
                union(left, right)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(observations)):
        grouped[find(index)].append(index)

    clusters = []
    for indices in grouped.values():
        rows = [observations[index] for index in indices]
        counts = Counter(token for index in indices for token in token_sets[index])
        anchors = sorted(token for token, count in counts.items() if count >= 2)
        clusters.append((rows, anchors))
    return clusters


class HorizonEmergingService:
    """Build unconfirmed multi-domain event hypotheses from closed GDELT buckets.

    Discovery is deliberately separated from factual confirmation. Repetition in
    GDELT remains one `news_global` evidence family. Candidate clustering also
    requires episode-level lexical overlap so unrelated stories of the same type
    are not merged solely because they happened in the same time bucket.
    """

    def __init__(self, db: Session):
        self.db = db

    def cluster_gdelt(
        self,
        request: HorizonEmergingClusterRequest,
        *,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.utcnow()
        current_bucket = _bucket_start(now, request.bucket_minutes)
        earliest = current_bucket - timedelta(minutes=request.bucket_minutes * request.lookback_buckets)
        source = self.db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one_or_none()
        if source is None:
            HorizonSourceService(self.db).sync_builtin_sources()
            source = self.db.query(HorizonSource).filter(HorizonSource.source_key == "gdelt-doc-2").one()

        rows = (
            self.db.query(HorizonRawObservation)
            .filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.observation_type == "news_report",
                HorizonRawObservation.observed_at >= earliest,
                HorizonRawObservation.observed_at < current_bucket,
            )
            .order_by(HorizonRawObservation.observed_at.asc(), HorizonRawObservation.id.asc())
            .all()
        )

        bucketed: dict[tuple[datetime, str], list[HorizonRawObservation]] = defaultdict(list)
        ignored_unclassified = 0
        for row in rows:
            event_type = _classify(row)
            if event_type is None:
                ignored_unclassified += 1
                continue
            bucketed[(_bucket_start(row.observed_at, request.bucket_minutes), event_type)].append(row)

        results: list[dict] = []
        below_threshold = 0
        episode_groups_considered = 0
        source_service = HorizonSourceService(self.db)
        for (bucket, event_type), observations in sorted(bucketed.items(), key=lambda item: item[0]):
            bucket_end = bucket + timedelta(minutes=request.bucket_minutes)
            for episode_rows, anchor_tokens in _episode_clusters(observations):
                episode_groups_considered += 1
                if len(episode_rows) < request.min_articles or not anchor_tokens:
                    below_threshold += 1
                    continue
                selected = episode_rows[:100]
                family = str((selected[0].canonical_facts or {}).get("watch_family") or "")
                candidate = source_service.build_candidate(
                    HorizonCandidateBuild(
                        observation_ids=[item.id for item in selected],
                        event_type=event_type,
                        title=EVENT_TITLES.get(event_type, f"Emerging {event_type} episode"),
                        geography=[],
                        normalized_facts={
                            "fact_status": "unconfirmed_emerging_event",
                            "candidate_not_fact": True,
                            "raw_claims_verified": False,
                            "detection_basis": "multi_article_single_radar_episode_cluster",
                            "watch_family": family,
                            "article_count": len(selected),
                            "bucket_start": bucket.isoformat(),
                            "bucket_end": bucket_end.isoformat(),
                            "cluster_anchor_tokens": anchor_tokens[:24],
                            "episode_clustering_required": True,
                            "geography_status": "unknown",
                            "source_key": source.source_key,
                            "source_class": source.source_class,
                        },
                        normalizer_version=NORMALIZER_VERSION,
                    )
                )
                readiness = source_service.promotion_readiness(candidate)
                results.append({
                    "candidate_id": candidate.id,
                    "candidate_key": candidate.candidate_key,
                    "event_type": candidate.event_type,
                    "title": candidate.title,
                    "first_observed_at": candidate.first_observed_at,
                    "last_observed_at": candidate.last_observed_at,
                    "article_count": len(selected),
                    "cluster_anchor_tokens": anchor_tokens[:24],
                    "fact_status": "unconfirmed_emerging_event",
                    "promotion_ready": readiness["ready"],
                    "promotion_rule": readiness["rule"],
                    "corroboration_score": candidate.corroboration_score,
                    "corroboration_score_is_probability": False,
                })

        return {
            "source_key": source.source_key,
            "normalizer_version": NORMALIZER_VERSION,
            "closed_bucket_end": current_bucket,
            "lookback_start": earliest,
            "raw_observations_scanned": len(rows),
            "ignored_unclassified": ignored_unclassified,
            "episode_groups_considered": episode_groups_considered,
            "groups_below_threshold": below_threshold,
            "candidates": results,
            "candidate_count": len(results),
            "candidate_event_types": sorted({item["event_type"] for item in results}),
            "candidates_are_confirmed_facts": False,
            "automatic_promotion_performed": False,
            "single_source_repetition_can_confirm_fact": False,
        }
