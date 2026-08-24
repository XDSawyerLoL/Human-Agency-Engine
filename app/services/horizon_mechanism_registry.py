from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern
from .horizon_corpus import HorizonCalibrationCorpusService


REGISTRY_VERSION = "horizon-mechanism-registry-v0.1"

# A mechanism contract is stricter than a behavior pattern. It declares what
# HORIZON can actually observe and replay, rather than merely what is plausible.
MECHANISM_CONTRACTS = (
    {
        "mechanism_key": "regional-heat-to-cooling-load-v1",
        "domains": ["weather_climate", "energy"],
        "pattern_key": "builtin-extreme-heat-regional-cooling-load-v1",
        "event_types": ["extreme_heat_region"],
        "outcome_signal_types": ["cooling_load_pressure"],
        "corpus_strategies": ["heat-mf-rte-v1"],
        "trigger_replay": {
            "status": "implemented",
            "source_family": "meteofrance-vigilance-archive",
            "point_in_time": True,
            "coverage_semantics": "explicit_interval_completeness",
        },
        "outcome_replay": {
            "status": "implemented",
            "source_family": "rte-eco2mix-regional-cons-def",
            "point_in_time": True,
            "coverage_semantics": "explicit_interval_completeness",
        },
    },
    {
        "mechanism_key": "regional-cold-to-heating-load-v1",
        "domains": ["weather_climate", "energy"],
        "pattern_key": "builtin-extreme-cold-regional-heating-load-v1",
        "event_types": ["extreme_cold_region"],
        "outcome_signal_types": ["heating_load_pressure"],
        "corpus_strategies": ["cold-mf-rte-v1"],
        "trigger_replay": {
            "status": "implemented",
            "source_family": "meteofrance-vigilance-archive",
            "point_in_time": True,
            "coverage_semantics": "explicit_interval_completeness",
        },
        "outcome_replay": {
            "status": "implemented",
            "source_family": "rte-eco2mix-regional-cons-def",
            "point_in_time": True,
            "coverage_semantics": "explicit_interval_completeness",
        },
    },
    {
        "mechanism_key": "heat-to-cooling-purchase-pressure-v1",
        "domains": ["weather_climate", "supply_fuel"],
        "pattern_key": "builtin-extreme-heat-cooling-demand-v1",
        "event_types": ["extreme_heat"],
        "outcome_signal_types": ["purchase_velocity", "inventory_pressure", "stockout_reports"],
        "corpus_strategies": [],
        "trigger_replay": {
            "status": "partial",
            "source_family": "weather-warning-and-live-signals",
            "point_in_time": True,
            "coverage_semantics": "not_complete_for_behavioral_outcomes",
        },
        "outcome_replay": {
            "status": "missing",
            "source_family": None,
            "point_in_time": False,
            "coverage_semantics": "no_historical_outcome_stream",
        },
    },
    {
        "mechanism_key": "supply-risk-to-precautionary-buying-v1",
        "domains": ["supply_fuel"],
        "pattern_key": "builtin-supply-risk-precautionary-buying-v1",
        "event_types": ["supply_disruption", "fuel_supply_disruption", "critical_goods_disruption"],
        "outcome_signal_types": ["precautionary_buying", "inventory_pressure", "shortage_reports", "stockout_reports"],
        "corpus_strategies": [],
        "trigger_replay": {
            "status": "missing",
            "source_family": None,
            "point_in_time": False,
            "coverage_semantics": "no_implemented_historical_trigger_replay",
        },
        "outcome_replay": {
            "status": "candidate_unwired",
            "source_family": "fr-government-fuel-annual-stock",
            "point_in_time": True,
            "coverage_semantics": "provider_annual_stock_candidate_not_implemented",
            "provenance": {
                "source": "Prix des carburants - données publiques",
                "locator": "https://www.prix-carburants.gouv.fr/rubrique/opendata/",
                "note": "Government open data exposes stock ruptures and annual stocks; HORIZON has not yet implemented a coverage-aware historical adapter.",
            },
        },
    },
    {
        "mechanism_key": "transit-disruption-to-mode-substitution-v1",
        "domains": ["transport_mobility"],
        "pattern_key": "builtin-transit-disruption-mode-substitution-v1",
        "event_types": ["rail_transport_disruption", "transport_disruption"],
        "outcome_signal_types": ["road_congestion", "crowding", "travel_time_deterioration", "delay_pressure"],
        "corpus_strategies": [],
        "trigger_replay": {
            "status": "missing",
            "source_family": None,
            "point_in_time": False,
            "coverage_semantics": "no_implemented_historical_disruption_archive",
        },
        "outcome_replay": {
            "status": "missing",
            "source_family": None,
            "point_in_time": False,
            "coverage_semantics": "no_implemented_historical_congestion_outcome_stream",
        },
    },
)


def _historical_pipeline_declared(contract: dict) -> bool:
    return (
        bool(contract.get("corpus_strategies"))
        and (contract.get("trigger_replay") or {}).get("status") == "implemented"
        and (contract.get("outcome_replay") or {}).get("status") == "implemented"
        and bool((contract.get("trigger_replay") or {}).get("point_in_time"))
        and bool((contract.get("outcome_replay") or {}).get("point_in_time"))
    )


def historically_calibratable_event_types() -> set[str]:
    values: set[str] = set()
    for contract in MECHANISM_CONTRACTS:
        if _historical_pipeline_declared(contract):
            values.update(str(item) for item in contract.get("event_types") or [])
    return values


class HorizonMechanismRegistryService:
    ENGINE_VERSION = REGISTRY_VERSION

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def contracts() -> tuple[dict, ...]:
        return MECHANISM_CONTRACTS

    def snapshot(self) -> dict:
        patterns = {
            row.pattern_key: row
            for row in self.db.query(HorizonBehaviorPattern)
            .filter(HorizonBehaviorPattern.status == "active")
            .all()
        }
        available_strategies = set(HorizonCalibrationCorpusService.STRATEGIES)

        mechanisms = []
        state_counts: dict[str, int] = defaultdict(int)
        for contract in MECHANISM_CONTRACTS:
            pattern_key = str(contract["pattern_key"])
            pattern = patterns.get(pattern_key)
            strategy_keys = [str(item) for item in contract.get("corpus_strategies") or []]
            strategies_configured = bool(strategy_keys) and all(
                item in available_strategies for item in strategy_keys
            )
            historical_declared = _historical_pipeline_declared(contract)

            if historical_declared and strategies_configured and pattern is not None:
                readiness = "historically_calibratable"
            elif historical_declared and strategies_configured:
                readiness = "historical_pipeline_present_pattern_unsynced"
            elif (contract.get("outcome_replay") or {}).get("status") == "candidate_unwired":
                readiness = "outcome_archive_candidate"
            else:
                readiness = "behavior_hypothesis_only"

            state_counts[readiness] += 1
            mechanisms.append({
                **contract,
                "pattern_registered": pattern is not None,
                "pattern_id": None if pattern is None else pattern.id,
                "knowledge_available_at": None if pattern is None else pattern.knowledge_available_at,
                "strategies_configured": strategies_configured,
                "calibration_readiness": readiness,
                "negative_labels_require_complete_outcome_coverage": True,
                "provider_failure_is_negative_outcome": False,
                "diagnostic_confidence_is_probability": False,
                "numeric_probabilities_enabled": False,
            })

        return {
            "engine": self.ENGINE_VERSION,
            "registry_version": REGISTRY_VERSION,
            "mechanisms": mechanisms,
            "readiness_counts": dict(sorted(state_counts.items())),
            "historically_calibratable_event_types": sorted(
                historically_calibratable_event_types()
            ),
            "critical_semantics": {
                "behavior_pattern_is_calibration_proof": False,
                "historical_trigger_replay_required": True,
                "historical_outcome_replay_required": True,
                "point_in_time_replay_required": True,
                "complete_outcome_coverage_required_for_negative_label": True,
                "provider_failure_is_negative_evidence": False,
                "numeric_probabilities_enabled": False,
            },
        }
