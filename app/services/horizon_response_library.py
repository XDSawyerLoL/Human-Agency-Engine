from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern
from .horizon_cold_response import COLD_PATTERN


LIBRARY_VERSION = "human-response-library-v0.5-multidomain"

# Conservative priors: behavioral hypotheses, not calibrated probabilities.
# support_count / contradiction_count stay zero until HORIZON's own point-in-time
# outcome evaluation creates labels.
BUILTIN_PATTERNS = (
    {
        "pattern_key": "builtin-extreme-heat-cooling-demand-v1",
        "name": "Extreme heat → cooling demand cascade",
        "event_types": ["extreme_heat"],
        "required_signal_types": [],
        "predicted_response": (
            "An extreme-heat warning can be followed by increasing attention to cooling, "
            "accelerating purchases of cooling equipment, inventory compression and visible shortages."
        ),
        "mechanism_chain": [
            "heat threat perception",
            "cooling search acceleration",
            "purchase acceleration",
            "inventory compression",
            "visible cooling-equipment shortage",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 168,
        "confidence": 0.52,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2022, 10, 1, 0, 0, 0),
        "provenance": {
            "library_version": "human-response-library-v0.1",
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["media_attention", "heat_attention"],
                "1": ["search_interest", "cooling_search_interest"],
                "2": ["purchase_velocity", "retail_demand"],
                "3": ["stock_availability", "inventory_pressure"],
                "4": ["shortage_reports", "stockout_reports"],
            },
            "evidence": [
                {
                    "kind": "peer_reviewed",
                    "title": "The weather affects air conditioner purchases to fill the energy efficiency gap",
                    "published": "2022-10-01",
                    "doi": "10.1038/s41467-022-33531-2",
                    "locator": "https://www.nature.com/articles/s41467-022-33531-2",
                    "note": "Transaction-level US data from 2006–2019 show short-run temperature changes materially affect air-conditioner purchase behavior.",
                },
                {
                    "kind": "market_observation",
                    "source": "Financial Times",
                    "published": "2026-08-16",
                    "locator": "https://www.ft.com/content/1419012f-feca-4efd-a817-dc0392cd76e3",
                    "note": "European firms reported sharply higher demand for fans and other heat-adaptation products during extreme heat.",
                },
            ],
            "limitations": [
                "Evidence supports heat-driven changes in cooling purchases, not a universal shortage cascade.",
                "The inventory-compression and stockout stages require independent live evidence before HORIZON may mark them reached.",
                "Local inventory, housing, income and forecast severity can materially alter the response.",
            ],
        },
    },
    {
        "pattern_key": "builtin-supply-risk-precautionary-buying-v1",
        "name": "Supply disruption risk → precautionary buying cascade",
        "event_types": ["supply_disruption", "fuel_supply_disruption", "critical_goods_disruption"],
        "required_signal_types": [],
        "predicted_response": (
            "A credible supply-disruption threat can increase perceived scarcity and social learning, "
            "which may accelerate precautionary purchases and queues and can amplify a real stockout."
        ),
        "mechanism_chain": [
            "supply threat perception",
            "perceived scarcity and social proof",
            "precautionary purchase acceleration",
            "queue and inventory pressure",
            "visible shortage or stockout",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 168,
        "confidence": 0.58,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2022, 5, 1, 0, 0, 0),
        "provenance": {
            "library_version": "human-response-library-v0.1",
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["media_attention", "supply_risk_attention"],
                "1": ["scarcity_search", "scarcity_mentions", "queue_reports"],
                "2": ["purchase_velocity", "precautionary_buying"],
                "3": ["queue_density", "inventory_pressure", "stock_availability"],
                "4": ["shortage_reports", "stockout_reports"],
            },
            "evidence": [
                {
                    "kind": "peer_reviewed",
                    "title": "Social determinants of panic buying behaviour amidst COVID-19 pandemic: The role of perceived scarcity and anticipated regret",
                    "published": "2022-05",
                    "doi": "10.1016/j.jretconser.2022.102948",
                    "locator": "https://www.sciencedirect.com/science/article/pii/S0969698922000418",
                    "note": "Social influence, social norms and observational learning increased perceived scarcity, which in turn was associated with panic buying.",
                },
                {
                    "kind": "peer_reviewed",
                    "title": "Why did all the toilet paper disappear? Distinguishing between panic buying and hoarding during COVID-19",
                    "published": "2021-09",
                    "doi": "10.1016/j.psychres.2021.114062",
                    "locator": "https://www.sciencedirect.com/science/article/pii/S0165178121003590",
                    "note": "Perceived scarcity was the strongest predictor of panic buying in the study sample.",
                },
                {
                    "kind": "peer_reviewed_model",
                    "title": "Supply disruption management under consumer panic buying and social learning effects",
                    "published": "2021-06",
                    "doi": "10.1016/j.omega.2020.102238",
                    "locator": "https://www.sciencedirect.com/science/article/pii/S0305048319307959",
                    "note": "Models purchase decisions under supply disruption risk with social-learning effects.",
                },
            ],
            "limitations": [
                "Evidence comes from specific crises and populations and must not be treated as a universal behavioral law.",
                "Precautionary purchasing can be rational; the library does not label all increased purchasing as panic.",
                "HORIZON must use live behavioral evidence before asserting that a cascade is advancing.",
            ],
        },
    },
    {
        "pattern_key": "builtin-extreme-heat-regional-cooling-load-v1",
        "name": "Regional extreme heat → electricity cooling-load pressure",
        "event_types": ["extreme_heat_region"],
        "required_signal_types": [],
        "predicted_response": (
            "A multi-department extreme-heat episode may be followed by measurable regional afternoon "
            "electricity-load pressure consistent with increased cooling and HVAC use."
        ),
        "mechanism_chain": [
            "multi-department heat exposure",
            "increased cooling and HVAC use",
            "regional afternoon electricity-load pressure",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 72,
        "confidence": 0.60,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2021, 10, 1, 0, 0, 0),
        "provenance": {
            "library_version": "human-response-library-v0.2-additive",
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "materialization_signal_types": ["cooling_load_pressure"],
            "materialization_min_reliability": 0.85,
            "materialization_strong_source_reliability": 0.90,
            "materialization_min_normalized_score": 1.0,
            "forecast_expiry_grace_hours": 24,
            "stage_signal_types": {
                "0": ["heat_attention", "weather_model_consensus"],
                "1": ["cooling_load_pressure"],
            },
            "evidence": [
                {
                    "kind": "official_system_study",
                    "source": "RTE",
                    "title": "Futurs énergétiques 2050 — Climat et système électrique",
                    "published": "2021-10",
                    "locator": "https://assets.rte-france.com/prod/public/2021-10/BP2050_rapport-complet_chapitre8_climat-systeme-electrique.pdf",
                    "note": "RTE documents summer temperature sensitivity of French electricity demand and increasing air-conditioning consumption under warming.",
                }
            ],
            "limitations": [
                "Regional aggregate electricity load does not prove that a particular increase was caused by air conditioning.",
                "The signal is an observable collective load outcome, not a measurement of cooling-equipment purchases or retail shortages.",
                "Calendar, tourism, industrial activity and other demand drivers can alter regional electricity consumption.",
                "HORIZON therefore treats RTE load pressure as a behavioral outcome proxy and preserves the no-causality claim explicitly.",
            ],
        },
    },
    {
        "pattern_key": "builtin-transit-disruption-mode-substitution-v1",
        "name": "Public-transport disruption → mode substitution and road congestion",
        "event_types": ["rail_transport_disruption", "transport_disruption"],
        "required_signal_types": [],
        "predicted_response": (
            "A substantial public-transport disruption can push some travelers toward substitute routes and modes, "
            "which may increase road congestion, crowd alternative services and lengthen door-to-door travel times."
        ),
        "mechanism_chain": [
            "public-transport capacity loss",
            "traveler route and mode substitution",
            "alternative-network demand pressure",
            "road or substitute-service congestion",
            "observable travel-time deterioration",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 24,
        "confidence": 0.56,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2014, 9, 1, 0, 0, 0),
        "provenance": {
            "library_version": LIBRARY_VERSION,
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["transport_service_loss", "rail_service_disruption"],
                "1": ["route_search_shift", "mode_substitution"],
                "2": ["road_demand_pressure", "alternative_service_demand"],
                "3": ["road_congestion", "crowding", "queue_density"],
                "4": ["travel_time_deterioration", "delay_pressure"],
            },
            "evidence": [
                {
                    "kind": "peer_reviewed_causal_study",
                    "source": "American Economic Review",
                    "title": "Subways, Strikes, and Slowdowns: The Impacts of Public Transit on Traffic Congestion",
                    "author": "Michael L. Anderson",
                    "published": "2014-09",
                    "doi": "10.1257/aer.104.9.2763",
                    "locator": "https://www.aeaweb.org/articles?id=10.1257/aer.104.9.2763",
                    "note": "During the 2003 Los Angeles transit strike, average highway delay increased 47 percent; the estimate is context-specific evidence for mode-substitution pressure, not a universal effect size.",
                }
            ],
            "limitations": [
                "The causal estimate comes from one metropolitan transport strike and must not be transported as a universal 47 percent forecast.",
                "Network topology, car ownership, remote-work options, time of day and substitute capacity materially change the response.",
                "HORIZON must observe independent congestion, crowding or travel-time evidence before marking downstream stages reached.",
            ],
        },
    },
    {
        "pattern_key": "builtin-mass-layoff-local-labor-pressure-v1",
        "name": "Mass layoff / industrial closure → local labor-market pressure",
        "event_types": ["mass_layoff", "industrial_closure"],
        "required_signal_types": [],
        "predicted_response": (
            "A large layoff or industrial-site closure can rapidly increase job-search activity and "
            "the local supply of workers with similar skills, raising competition for nearby roles "
            "and demand for placement, retraining and income-support services."
        ),
        "mechanism_chain": [
            "employment shock becomes salient",
            "affected workers begin job search",
            "local labor supply rises in overlapping occupations",
            "competition for similar vacancies increases",
            "placement and retraining demand rises",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 720,
        "confidence": 0.54,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2011, 1, 1, 0, 0, 0),
        "provenance": {
            "library_version": LIBRARY_VERSION,
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["layoff_attention", "closure_attention"],
                "1": ["job_search_interest", "job_search_activity"],
                "2": ["job_applications", "labor_supply_pressure"],
                "3": ["vacancy_competition", "placement_delay"],
                "4": ["retraining_demand", "income_support_demand"],
            },
            "evidence": [
                {
                    "kind": "labor_economics",
                    "title": "Recessions and the Costs of Job Loss",
                    "authors": "Steven J. Davis and Till von Wachter",
                    "published": "2011",
                    "note": (
                        "Displaced workers can experience persistent employment and earnings losses; "
                        "HORIZON uses this only as evidence that large displacement shocks create real "
                        "labor-market adjustment pressure, not as a local effect-size estimate."
                    ),
                }
            ],
            "limitations": [
                "A company announcement does not prove how many workers will actually enter the local job market.",
                "Remote work, severance, commuting, occupational mix and local vacancy demand can materially change the response.",
                "HORIZON has no complete historical job-search or vacancy outcome stream for this mechanism yet.",
            ],
        },
    },
    {
        "pattern_key": "builtin-sanctions-trade-friction-price-pressure-v1",
        "name": "Sanctions / trade restriction → supply and price pressure",
        "event_types": ["economic_sanctions", "trade_policy_change", "energy_supply_disruption"],
        "required_signal_types": [],
        "predicted_response": (
            "A material sanction, tariff or trade restriction can increase import friction and "
            "rerouting costs, reduce accessible supply in exposed sectors and create downstream "
            "price or availability pressure."
        ),
        "mechanism_chain": [
            "trade restriction becomes credible",
            "import or settlement friction rises",
            "firms reroute or substitute supply",
            "accessible supply or margins compress",
            "sector price or availability pressure becomes visible",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 720,
        "confidence": 0.55,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2019, 11, 1, 0, 0, 0),
        "provenance": {
            "library_version": LIBRARY_VERSION,
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["sanctions_attention", "trade_policy_attention"],
                "1": ["import_friction", "shipping_rerouting", "settlement_friction"],
                "2": ["supplier_substitution", "inventory_pressure"],
                "3": ["wholesale_price_pressure", "availability_pressure"],
                "4": ["consumer_price_pressure", "shortage_reports"],
            },
            "evidence": [
                {
                    "kind": "peer_reviewed_trade_economics",
                    "title": "The Impact of the 2018 Tariffs on Prices and Welfare",
                    "authors": "Mary Amiti, Stephen J. Redding and David E. Weinstein",
                    "published": "2019",
                    "doi": "10.1257/jep.33.4.187",
                    "note": (
                        "The study documents substantial tariff pass-through in the 2018 US episode. "
                        "HORIZON treats it as mechanism evidence, not as a universal price-impact estimate."
                    ),
                }
            ],
            "limitations": [
                "Sanctions, tariffs and export controls differ substantially in scope and enforcement.",
                "Exchange rates, inventories, substitution and government intervention can absorb or amplify price effects.",
                "HORIZON must observe independent supply or price outcomes before claiming downstream materialization.",
            ],
        },
    },
    {
        "pattern_key": "builtin-civil-unrest-mobility-disruption-v1",
        "name": "Collective unrest / strike action → local mobility and activity disruption",
        "event_types": ["civil_unrest", "mass_protest", "strike_action"],
        "required_signal_types": [],
        "predicted_response": (
            "Large collective action can lead authorities, operators, workers and travelers to alter "
            "routes, schedules or opening decisions, creating localized mobility and activity disruption."
        ),
        "mechanism_chain": [
            "collective action becomes salient",
            "participants and operators change behavior",
            "access or service capacity becomes uncertain",
            "route and schedule substitution increases",
            "localized mobility or activity disruption becomes visible",
        ],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 48,
        "confidence": 0.50,
        "support_count": 0,
        "contradiction_count": 0,
        "knowledge_available_at": datetime(2014, 1, 1, 0, 0, 0),
        "provenance": {
            "library_version": LIBRARY_VERSION,
            "status": "provisional_prior",
            "formal_probability": False,
            "calibrated_on_horizon_outcomes": False,
            "stage_signal_types": {
                "0": ["protest_attention", "strike_attention", "civil_unrest_attention"],
                "1": ["operator_schedule_change", "route_avoidance"],
                "2": ["service_capacity_pressure", "access_restriction"],
                "3": ["crowding", "road_congestion", "business_closure_reports"],
                "4": ["travel_time_deterioration", "activity_disruption"],
            },
            "evidence": [
                {
                    "kind": "mechanism_definition",
                    "note": (
                        "The hypothesis is deliberately narrow: strikes, blockades and large gatherings "
                        "can alter access or service capacity. It does not assume that every protest causes disruption."
                    ),
                }
            ],
            "limitations": [
                "Peaceful demonstrations may have little or no measurable disruption.",
                "Location, route, duration, policing, transport redundancy and remote-work options strongly affect outcomes.",
                "The current evidence path is discovery-first and is not historically calibrated.",
            ],
        },
    },
    COLD_PATTERN,
)


class HorizonResponseLibraryService:
    def __init__(self, db: Session):
        self.db = db

    def sync_builtins(self) -> list[HorizonBehaviorPattern]:
        rows: list[HorizonBehaviorPattern] = []
        for spec in BUILTIN_PATTERNS:
            row = self.db.query(HorizonBehaviorPattern).filter(
                HorizonBehaviorPattern.pattern_key == spec["pattern_key"]
            ).one_or_none()
            if row is None:
                row = HorizonBehaviorPattern(**spec, status="active")
                self.db.add(row)
            else:
                # Versioned built-ins are immutable. New science/mechanisms require
                # a new pattern key so old backtests retain their historical knowledge set.
                expected = {key: value for key, value in spec.items() if key not in {"knowledge_available_at"}}
                actual = {
                    "pattern_key": row.pattern_key,
                    "name": row.name,
                    "event_types": row.event_types,
                    "required_signal_types": row.required_signal_types,
                    "predicted_response": row.predicted_response,
                    "mechanism_chain": row.mechanism_chain,
                    "expected_lag_hours_low": row.expected_lag_hours_low,
                    "expected_lag_hours_high": row.expected_lag_hours_high,
                    "confidence": row.confidence,
                    "support_count": row.support_count,
                    "contradiction_count": row.contradiction_count,
                    "provenance": row.provenance,
                }
                if actual != expected or row.knowledge_available_at != spec["knowledge_available_at"]:
                    raise ValueError(f"built-in behavior pattern {row.pattern_key} differs from immutable library version")
            rows.append(row)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def list_builtins(self) -> list[HorizonBehaviorPattern]:
        keys = [item["pattern_key"] for item in BUILTIN_PATTERNS]
        return (
            self.db.query(HorizonBehaviorPattern)
            .filter(HorizonBehaviorPattern.pattern_key.in_(keys))
            .order_by(HorizonBehaviorPattern.pattern_key.asc())
            .all()
        )
