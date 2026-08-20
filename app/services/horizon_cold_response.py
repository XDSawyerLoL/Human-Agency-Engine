from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern


COLD_PATTERN = {
    "pattern_key": "builtin-extreme-cold-regional-heating-load-v1",
    "name": "Regional extreme cold → electricity heating-load pressure",
    "event_types": ["extreme_cold_region"],
    "required_signal_types": [],
    "predicted_response": (
        "A multi-department extreme-cold episode may be followed by measurable regional "
        "electricity-load pressure consistent with increased electric heating demand."
    ),
    "mechanism_chain": [
        "multi-department cold exposure",
        "increased electric heating demand",
        "regional all-day electricity-load pressure",
    ],
    "expected_lag_hours_low": 0,
    "expected_lag_hours_high": 72,
    "confidence": 0.66,
    "support_count": 0,
    "contradiction_count": 0,
    "knowledge_available_at": datetime(2021, 10, 1, 0, 0, 0),
    "provenance": {
        "library_version": "human-response-library-v0.3-additive-cold",
        "status": "provisional_prior",
        "formal_probability": False,
        "calibrated_on_horizon_outcomes": False,
        "materialization_signal_types": ["heating_load_pressure"],
        "materialization_min_reliability": 0.85,
        "materialization_strong_source_reliability": 0.90,
        "materialization_min_normalized_score": 1.0,
        "forecast_expiry_grace_hours": 24,
        "stage_signal_types": {
            "0": ["cold_attention", "weather_warning"],
            "1": ["heating_load_pressure"],
        },
        "evidence": [
            {
                "kind": "official_system_study",
                "source": "RTE",
                "title": "Futurs énergétiques 2050 — Climat et système électrique",
                "published": "2021-10",
                "locator": "https://assets.rte-france.com/prod/public/2021-10/BP2050_rapport-complet_chapitre8_climat-systeme-electrique.pdf",
                "note": (
                    "RTE documents strong winter thermosensitivity in France: below 15°C, a 1°C "
                    "temperature decrease is associated with roughly 2.4 GW additional electricity demand."
                ),
            },
            {
                "kind": "official_system_study",
                "source": "RTE",
                "title": "Futurs énergétiques 2050 — La consommation",
                "published": "2021-10",
                "locator": "https://assets.rte-france.com/prod/public/2021-10/BP2050_rapport-complet_chapitre3_consommation_0.pdf",
                "note": (
                    "RTE identifies electric heating as a major driver of winter demand and notes that "
                    "intense cold waves can significantly increase called power."
                ),
            },
        ],
        "limitations": [
            "Regional aggregate electricity load does not prove that a particular increase was caused by electric heating.",
            "Industrial activity, calendar effects, holidays and other demand drivers can alter regional electricity consumption.",
            "The signal is an observed collective load proxy, not a household-level behavioral measurement.",
        ],
    },
}


class HorizonColdResponseLibraryService:
    def __init__(self, db: Session):
        self.db = db

    def sync(self) -> HorizonBehaviorPattern:
        row = self.db.query(HorizonBehaviorPattern).filter(
            HorizonBehaviorPattern.pattern_key == COLD_PATTERN["pattern_key"]
        ).one_or_none()
        if row is None:
            row = HorizonBehaviorPattern(**COLD_PATTERN, status="active")
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row

        expected = {
            key: value
            for key, value in COLD_PATTERN.items()
            if key != "knowledge_available_at"
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
        if actual != expected or row.knowledge_available_at != COLD_PATTERN["knowledge_available_at"]:
            raise ValueError(
                f"built-in behavior pattern {row.pattern_key} differs from immutable cold-library version"
            )
        return row
