from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern
from ..horizon_source_models import HorizonSource


DOMAIN_CONTRACTS = (
    {"domain": "weather_climate", "label": "Weather & climate", "target_maturity": "historically_calibratable", "event_types": ["extreme_heat", "extreme_heat_region", "extreme_cold", "extreme_cold_region", "drought"], "source_domains": ["weather", "forecast_models"]},
    {"domain": "natural_hazards", "label": "Natural hazards", "target_maturity": "live_multi_source", "event_types": ["flood", "river_flood_risk", "wildfire", "earthquake", "tropical_cyclone", "volcano"], "source_domains": ["disasters", "civil_protection"]},
    {"domain": "transport_mobility", "label": "Transport & mobility", "target_maturity": "historically_calibratable", "event_types": ["rail_transport_disruption", "transport_disruption"], "source_domains": ["transport", "rail"]},
    {"domain": "supply_fuel", "label": "Supply chains & fuel", "target_maturity": "historically_calibratable", "event_types": ["supply_disruption", "fuel_supply_disruption", "critical_goods_disruption"], "source_domains": ["fuel", "supply", "retail"]},
    {"domain": "energy", "label": "Energy", "target_maturity": "historically_calibratable", "event_types": ["energy_supply_disruption", "energy_market_stress", "power_grid_disruption"], "source_domains": ["electricity", "energy"]},
    {"domain": "media_attention", "label": "Media & collective attention", "target_maturity": "live_multi_source", "event_types": [], "source_domains": ["news_attention", "world_events"]},
    {"domain": "geopolitics_security", "label": "Geopolitics & security", "target_maturity": "historically_calibratable", "event_types": ["geopolitical_conflict", "economic_sanctions", "political_instability"], "source_domains": ["geopolitics", "security", "world_events"]},
    {"domain": "economy_labor", "label": "Economy & labor", "target_maturity": "historically_calibratable", "event_types": ["mass_layoff", "corporate_distress", "industrial_closure"], "source_domains": ["economy", "labor", "world_events"]},
    {"domain": "public_health", "label": "Public health", "target_maturity": "historically_calibratable", "event_types": ["public_health_outbreak"], "source_domains": ["public_health", "health", "world_events"]},
    {"domain": "cyber_technology", "label": "Cyber & technology", "target_maturity": "historically_calibratable", "event_types": ["cyber_incident", "technology_service_outage", "internet_service_outage"], "source_domains": ["cyber", "technology", "world_events"]},
    {"domain": "regulation_policy", "label": "Regulation & policy", "target_maturity": "historically_calibratable", "event_types": ["regulatory_change", "trade_policy_change"], "source_domains": ["regulation", "policy", "world_events"]},
    {"domain": "financial_stress", "label": "Financial stress", "target_maturity": "historically_calibratable", "event_types": ["financial_stress"], "source_domains": ["finance", "economy", "world_events"]},
    {"domain": "personal_context", "label": "Personal context & exposure", "target_maturity": "personalized", "event_types": [], "source_domains": []},
)

HISTORICALLY_CALIBRATABLE_EVENT_TYPES = {"extreme_heat_region", "extreme_cold_region"}

LIVE_CONFIRMED_EVENT_TYPES = {
    "extreme_heat", "extreme_cold", "flood", "river_flood_risk", "wildfire", "earthquake",
    "tropical_cyclone", "rail_transport_disruption", "fuel_supply_disruption",
}

DISCOVERY_EVENT_TYPES = {
    "supply_disruption", "extreme_heat", "wildfire", "flood", "earthquake", "tropical_cyclone", "drought",
    "economic_sanctions", "political_instability", "geopolitical_conflict", "rail_transport_disruption",
    "internet_service_outage", "power_grid_disruption", "critical_infrastructure_outage", "mass_layoff",
    "industrial_closure", "corporate_distress", "public_health_outbreak", "trade_policy_change",
    "regulatory_change", "cyber_incident", "technology_service_outage", "financial_stress",
    "energy_supply_disruption", "energy_market_stress",
}


class HorizonWorldCoverageService:
    ENGINE_VERSION = "horizon-world-coverage-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _maturity(event_types: set[str], source_count: int, pattern_count: int) -> tuple[str, list[str]]:
        reasons: list[str] = []
        if event_types & HISTORICALLY_CALIBRATABLE_EVENT_TYPES:
            reasons.append("coverage-aware historical trigger/outcome replay exists")
            return "historically_calibratable", reasons
        confirmed = event_types & LIVE_CONFIRMED_EVENT_TYPES
        discovered = event_types & DISCOVERY_EVENT_TYPES
        if confirmed and source_count >= 2:
            reasons.append("live factual/operational evidence exists across multiple registered sources")
            if pattern_count:
                reasons.append("behavior pattern available")
            return "live_multi_source", reasons
        if confirmed and source_count >= 1:
            reasons.append("live factual/operational evidence exists from one registered source path")
            return "live_single_source", reasons
        if discovered:
            reasons.append("broad discovery creates unconfirmed hypotheses only")
            if pattern_count:
                reasons.append("behavior pattern available but factual confirmation/outcome coverage is incomplete")
            return "discovery_only", reasons
        if source_count:
            reasons.append("registered source exists but no complete event-to-outcome path is declared")
            return "source_only", reasons
        return "missing", ["no implemented evidence path yet"]

    def snapshot(self) -> dict:
        sources = self.db.query(HorizonSource).filter(HorizonSource.enabled == True).all()  # noqa: E712
        patterns = self.db.query(HorizonBehaviorPattern).filter(HorizonBehaviorPattern.status == "active").all()

        source_domains: dict[str, set[str]] = defaultdict(set)
        for source in sources:
            for domain in source.domains or []:
                source_domains[str(domain)].add(source.source_key)

        pattern_by_event: dict[str, set[str]] = defaultdict(set)
        for pattern in patterns:
            for event_type in pattern.event_types or []:
                pattern_by_event[str(event_type)].add(pattern.pattern_key)

        rows = []
        maturity_counts: dict[str, int] = defaultdict(int)
        for contract in DOMAIN_CONTRACTS:
            event_types = set(contract["event_types"])
            source_keys = sorted({source_key for domain in contract["source_domains"] for source_key in source_domains.get(domain, set())})
            pattern_keys = sorted({pattern_key for event_type in event_types for pattern_key in pattern_by_event.get(event_type, set())})
            if contract["domain"] == "personal_context":
                maturity = "personalized"
                reasons = ["state facts, intents and personal-scope relevance gate are implemented"]
            else:
                maturity, reasons = self._maturity(event_types, len(source_keys), len(pattern_keys))
            maturity_counts[maturity] += 1
            rows.append({
                **contract,
                "current_maturity": maturity,
                "registered_source_keys": source_keys,
                "behavior_pattern_keys": pattern_keys,
                "reasons": reasons,
            })

        return {
            "engine": self.ENGINE_VERSION,
            "product_scope": "domain_agnostic_personal_world_anticipation",
            "domains": rows,
            "maturity_counts": dict(sorted(maturity_counts.items())),
            "development_priority": [
                "add independent factual/operational sources outside weather",
                "add timestamped outcome streams with completeness semantics",
                "calibrate behavior mechanisms independently by domain",
                "retain personal exposure as the final relevance gate",
            ],
            "critical_semantics": {
                "weather_is_product_boundary": False,
                "discovery_is_confirmation": False,
                "source_count_is_probability": False,
                "diagnostic_maturity_is_probability": False,
                "numeric_probabilities_enabled": False,
            },
        }
