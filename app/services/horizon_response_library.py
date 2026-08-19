from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern


LIBRARY_VERSION = "human-response-library-v0.1"

# These are deliberately conservative priors. They are hypotheses backed by
# external research and business observations, not calibrated probabilities.
# support_count / contradiction_count stay at zero until HORIZON's own
# historical backtests create labels.
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
            "library_version": LIBRARY_VERSION,
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
        "event_types": [
            "supply_disruption",
            "fuel_supply_disruption",
            "critical_goods_disruption",
        ],
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
            "library_version": LIBRARY_VERSION,
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
)


class HorizonResponseLibraryService:
    def __init__(self, db: Session):
        self.db = db

    def sync_builtins(self) -> list[HorizonBehaviorPattern]:
        rows: list[HorizonBehaviorPattern] = []
        for spec in BUILTIN_PATTERNS:
            row = (
                self.db.query(HorizonBehaviorPattern)
                .filter(HorizonBehaviorPattern.pattern_key == spec["pattern_key"])
                .one_or_none()
            )
            if row is None:
                row = HorizonBehaviorPattern(**spec, status="active")
                self.db.add(row)
            else:
                # A versioned built-in pattern is immutable. Changing the science or
                # mechanism requires a new pattern_key/version rather than rewriting
                # what an old backtest was allowed to know.
                expected = {
                    key: value
                    for key, value in spec.items()
                    if key not in {"knowledge_available_at"}
                }
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
                    raise ValueError(
                        f"built-in behavior pattern {row.pattern_key} differs from immutable library version"
                    )
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
