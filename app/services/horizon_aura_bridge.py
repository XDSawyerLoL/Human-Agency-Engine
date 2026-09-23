from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .horizon_briefing import HorizonWorldBriefingService


class HorizonAuraBridgeService:
    """Stable machine-facing projection of HORIZON for AURA.

    The bridge deliberately preserves HORIZON's epistemic boundaries. Diagnostic
    and predictive scores are transported as metadata; they are never upgraded
    to probabilities or facts by the bridge.
    """

    BRIDGE_VERSION = "horizon-aura-bridge-v1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _fingerprint(kind: str, entity_id: Any, payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return f"{kind}:{entity_id}:{digest}"

    @staticmethod
    def _timestamp(value: Any) -> str:
        if value:
            return str(value)
        return datetime.now(timezone.utc).isoformat()

    def snapshot(
        self,
        *,
        external_id: str | None = None,
        event_limit: int = 100,
        candidate_limit: int = 100,
        forecast_limit: int = 100,
    ) -> dict[str, Any]:
        briefing = HorizonWorldBriefingService(self.db).snapshot(
            external_id=external_id,
            event_limit=event_limit,
            candidate_limit=candidate_limit,
            forecast_limit=forecast_limit,
        )
        signals: list[dict[str, Any]] = []

        for row in briefing["events"]:
            payload = {
                "kind": "confirmed_event",
                "entity_id": row["id"],
                "horizon_event_type": row["event_type"],
                "title": row["title"],
                "summary": row["summary"],
                "domain": row["domain"],
                "domain_label": row["domain_label"],
                "macro_category": row["macro_category"],
                "maturity": row["maturity"],
                "epistemic_status": row["fact_status"],
                "source": row["source"],
                "source_reliability": row["source_reliability"],
                "geography": row["geography"],
                "observed_at": row["observed_at"],
                "occurred_at": row["occurred_at"],
                "source_url": row["source_url"],
                "predictive_patterns": row["predictive_patterns"],
                "probability": None,
                "personal": False,
                "autonomy_hint": "verify_then_act",
            }
            signals.append(
                {
                    "signal_id": self._fingerprint("event", row["id"], payload),
                    "entity_key": f"event:{row['id']}",
                    "aura_event": "horizon.world.confirmed",
                    "observed_at": self._timestamp(row["observed_at"]),
                    "payload": payload,
                }
            )

        for row in briefing["hypotheses"]:
            payload = {
                "kind": "emerging_hypothesis",
                "entity_id": row["id"],
                "horizon_event_type": row["event_type"],
                "title": row["title"],
                "domain": row["domain"],
                "domain_label": row["domain_label"],
                "macro_category": row["macro_category"],
                "maturity": row["maturity"],
                "epistemic_status": row["fact_status"],
                "source_classes": row["source_classes"],
                "corroboration_score": row["corroboration_score"],
                "corroboration_score_is_probability": False,
                "geography": row["geography"],
                "observed_at": row["observed_at"],
                "first_observed_at": row["first_observed_at"],
                "provisional_forecasts": row["provisional_forecasts"],
                "probability": None,
                "personal": False,
                "autonomy_hint": "notify_or_verify_only",
            }
            signals.append(
                {
                    "signal_id": self._fingerprint("hypothesis", row["id"], payload),
                    "entity_key": f"hypothesis:{row['id']}",
                    "aura_event": "horizon.world.emerging",
                    "observed_at": self._timestamp(row["observed_at"]),
                    "payload": payload,
                }
            )

        for row in briefing["personal_forecasts"]:
            payload = {
                "kind": "personal_forecast",
                "entity_id": row["id"],
                "event_id": row["event_id"],
                "horizon_event_type": row["event_type"],
                "event_title": row["event_title"],
                "domain": row["domain"],
                "domain_label": row["domain_label"],
                "macro_category": row["macro_category"],
                "maturity": row["maturity"],
                "pattern_key": row["pattern_key"],
                "pattern_name": row["pattern_name"],
                "predicted_outcome": row["predicted_outcome"],
                "behavior_chain": row["behavior_chain"],
                "likelihood_band": row["likelihood_band"],
                "predictive_score": row["predictive_score"],
                "predictive_score_is_probability": False,
                "probability_interval": row["probability_interval"],
                "probability": None,
                "expected_onset_low": row["expected_onset_low"],
                "expected_onset_high": row["expected_onset_high"],
                "personal_exposure": row["personal_exposure"],
                "as_of": row["as_of"],
                "status": row["status"],
                "calibration_status": row["calibration_status"],
                "epistemic_status": "personal_forecast",
                "personal": True,
                "autonomy_hint": "personal_relevance_gate_then_propose",
            }
            signals.append(
                {
                    "signal_id": self._fingerprint("forecast", row["id"], payload),
                    "entity_key": f"forecast:{row['id']}",
                    "aura_event": "horizon.personal.forecast",
                    "observed_at": self._timestamp(row["as_of"]),
                    "payload": payload,
                }
            )

        signals.sort(key=lambda item: (item["observed_at"], item["signal_id"]))

        return {
            "bridge": self.BRIDGE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "external_id": external_id,
            "user_found": briefing["user_found"],
            "summary": {
                **briefing["summary"],
                "signals": len(signals),
            },
            "signals": signals,
            "signal_contract": {
                "horizon.world.confirmed": "Confirmed or derived HORIZON event. It is not automatically a raw fact.",
                "horizon.world.emerging": "Unconfirmed emerging hypothesis. Never treat corroboration_score as probability.",
                "horizon.personal.forecast": "Forecast that passed HORIZON's personal exposure surface for this user.",
            },
            "critical_semantics": {
                **briefing["critical_semantics"],
                "aura_must_preserve_epistemic_status": True,
                "emerging_hypothesis_may_trigger_irreversible_action": False,
                "scores_are_not_probabilities": True,
            },
        }

    @classmethod
    def capabilities(cls) -> dict[str, Any]:
        return {
            "bridge": cls.BRIDGE_VERSION,
            "direction": ["horizon_to_aura", "aura_to_horizon_context"],
            "events": [
                "horizon.world.confirmed",
                "horizon.world.emerging",
                "horizon.personal.forecast",
            ],
            "supports_personal_context": True,
            "supports_intents": True,
            "numeric_probabilities_enabled": False,
        }
