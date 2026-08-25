from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern, HorizonForecast, HorizonGlobalEvent
from ..horizon_provisional_models import HorizonProvisionalForecast
from ..horizon_source_models import HorizonEventCandidate
from ..models import User
from .horizon_world_coverage import DOMAIN_CONTRACTS, HorizonWorldCoverageService


MACRO_CATEGORY_BY_DOMAIN = {
    "weather_climate": "weather",
    "natural_hazards": "weather",
    "social_collective_behavior": "social",
    "media_attention": "social",
    "public_health": "social",
    "transport_mobility": "social",
    "economy_labor": "economy",
    "supply_fuel": "economy",
    "energy": "economy",
    "financial_stress": "economy",
    "regulation_policy": "economy",
    "geopolitics_security": "geopolitics",
    "cyber_technology": "infrastructure",
    "personal_context": "personal",
}

DOMAIN_LABELS = {item["domain"]: item["label"] for item in DOMAIN_CONTRACTS}
EVENT_DOMAIN = {
    event_type: item["domain"]
    for item in DOMAIN_CONTRACTS
    for event_type in item["event_types"]
}


def _domain_for_event(event_type: str) -> str:
    return EVENT_DOMAIN.get(str(event_type), "media_attention")


def _category_for_domain(domain: str) -> str:
    return MACRO_CATEGORY_BY_DOMAIN.get(domain, "other")


class HorizonWorldBriefingService:
    ENGINE_VERSION = "horizon-world-briefing-v0.2"

    def __init__(self, db: Session):
        self.db = db

    def snapshot(
        self,
        *,
        external_id: str | None = None,
        event_limit: int = 60,
        candidate_limit: int = 60,
        forecast_limit: int = 60,
    ) -> dict:
        coverage = HorizonWorldCoverageService(self.db).snapshot()
        maturity_by_domain = {
            item["domain"]: item["current_maturity"]
            for item in coverage["domains"]
        }

        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(HorizonGlobalEvent.status == "active")
            .order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
            .limit(event_limit)
            .all()
        )
        event_rows = []
        for row in events:
            domain = _domain_for_event(row.event_type)
            event_rows.append({
                "kind": "confirmed_event",
                "id": row.id,
                "event_type": row.event_type,
                "title": row.title,
                "summary": row.summary,
                "domain": domain,
                "domain_label": DOMAIN_LABELS.get(domain, domain),
                "macro_category": _category_for_domain(domain),
                "maturity": maturity_by_domain.get(domain, "missing"),
                "fact_status": "confirmed_or_derived_event",
                "source": row.source,
                "source_reliability": row.source_reliability,
                "geography": row.geography,
                "observed_at": row.first_observed_at.isoformat(),
                "occurred_at": row.occurred_at.isoformat(),
                "source_url": row.source_url,
                "probability": None,
            })

        candidates = (
            self.db.query(HorizonEventCandidate)
            .filter(
                HorizonEventCandidate.promotion_status == "candidate",
                HorizonEventCandidate.promoted_event_id.is_(None),
            )
            .order_by(HorizonEventCandidate.last_observed_at.desc(), HorizonEventCandidate.id.desc())
            .limit(candidate_limit)
            .all()
        )
        candidate_rows = []
        candidate_ids = []
        for row in candidates:
            domain = _domain_for_event(row.event_type)
            candidate_ids.append(row.id)
            candidate_rows.append({
                "kind": "emerging_hypothesis",
                "id": row.id,
                "event_type": row.event_type,
                "title": row.title,
                "summary": "",
                "domain": domain,
                "domain_label": DOMAIN_LABELS.get(domain, domain),
                "macro_category": _category_for_domain(domain),
                "maturity": maturity_by_domain.get(domain, "missing"),
                "fact_status": "unconfirmed_emerging_event",
                "source_classes": row.source_classes or [],
                "corroboration_score": float(row.corroboration_score),
                "corroboration_score_is_probability": False,
                "geography": row.geography or [],
                "observed_at": row.last_observed_at.isoformat(),
                "first_observed_at": row.first_observed_at.isoformat(),
                "probability": None,
            })

        provisional_by_candidate: dict[int, list[dict]] = defaultdict(list)
        if candidate_ids:
            provisional = (
                self.db.query(HorizonProvisionalForecast, HorizonBehaviorPattern)
                .join(HorizonBehaviorPattern, HorizonBehaviorPattern.id == HorizonProvisionalForecast.pattern_id)
                .filter(HorizonProvisionalForecast.candidate_id.in_(candidate_ids))
                .order_by(HorizonProvisionalForecast.as_of.desc(), HorizonProvisionalForecast.id.desc())
                .all()
            )
            for forecast, pattern in provisional:
                provisional_by_candidate[forecast.candidate_id].append({
                    "forecast_id": forecast.id,
                    "pattern_key": pattern.pattern_key,
                    "pattern_name": pattern.name,
                    "predicted_response": forecast.predicted_response,
                    "mechanism_chain": list(pattern.mechanism_chain or []),
                    "pattern_confidence": float(pattern.confidence),
                    "hypothesis_band": forecast.hypothesis_band,
                    "provisional_score": float(forecast.provisional_score),
                    "provisional_score_is_probability": False,
                    "relative_lag_hours": (forecast.interpretation or {}).get("relative_lag_hours"),
                    "fact_status": forecast.fact_status,
                    "user_surface_allowed": forecast.user_surface_allowed,
                })

        for item in candidate_rows:
            item["provisional_forecasts"] = provisional_by_candidate.get(item["id"], [])

        personal_forecasts = []
        user = None
        if external_id:
            user = self.db.query(User).filter(User.external_id == external_id).one_or_none()
        if user is not None:
            rows = (
                self.db.query(HorizonForecast, HorizonGlobalEvent, HorizonBehaviorPattern)
                .join(HorizonGlobalEvent, HorizonGlobalEvent.id == HorizonForecast.event_id)
                .join(HorizonBehaviorPattern, HorizonBehaviorPattern.id == HorizonForecast.pattern_id)
                .filter(HorizonForecast.user_id == user.id, HorizonForecast.mode == "live")
                .order_by(HorizonForecast.as_of.desc(), HorizonForecast.id.desc())
                .limit(forecast_limit)
                .all()
            )
            for forecast, event, pattern in rows:
                domain = _domain_for_event(event.event_type)
                personal_forecasts.append({
                    "kind": "personal_forecast",
                    "id": forecast.id,
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "event_title": event.title,
                    "domain": domain,
                    "domain_label": DOMAIN_LABELS.get(domain, domain),
                    "macro_category": _category_for_domain(domain),
                    "maturity": maturity_by_domain.get(domain, "missing"),
                    "pattern_key": pattern.pattern_key,
                    "pattern_name": pattern.name,
                    "predicted_outcome": forecast.predicted_outcome,
                    "behavior_chain": forecast.behavior_chain,
                    "likelihood_band": forecast.likelihood_band,
                    "predictive_score": float(forecast.predictive_score),
                    "predictive_score_is_probability": False,
                    "probability_interval": {
                        "low": forecast.probability_low,
                        "mid": forecast.probability_mid,
                        "high": forecast.probability_high,
                        "basis": forecast.probability_basis,
                    },
                    "expected_onset_low": forecast.expected_onset_low.isoformat() if forecast.expected_onset_low else None,
                    "expected_onset_high": forecast.expected_onset_high.isoformat() if forecast.expected_onset_high else None,
                    "personal_exposure": forecast.personal_exposure,
                    "as_of": forecast.as_of.isoformat(),
                    "status": forecast.status,
                    "calibration_status": forecast.calibration_status,
                })

        domain_counts: dict[str, dict] = defaultdict(lambda: {
            "confirmed_events": 0,
            "emerging_hypotheses": 0,
            "personal_forecasts": 0,
        })
        for item in event_rows:
            domain_counts[item["domain"]]["confirmed_events"] += 1
        for item in candidate_rows:
            domain_counts[item["domain"]]["emerging_hypotheses"] += 1
        for item in personal_forecasts:
            domain_counts[item["domain"]]["personal_forecasts"] += 1

        domains = []
        for row in coverage["domains"]:
            counts = domain_counts[row["domain"]]
            domains.append({
                "domain": row["domain"],
                "label": row["label"],
                "macro_category": _category_for_domain(row["domain"]),
                "current_maturity": row["current_maturity"],
                "target_maturity": row["target_maturity"],
                "registered_sources": len(row["registered_source_keys"]),
                "behavior_patterns": len(row["behavior_pattern_keys"]),
                "mechanisms": len(row["mechanism_keys"]),
                "historically_calibratable_mechanisms": len(
                    row["historically_calibratable_mechanism_keys"]
                ),
                **counts,
            })

        return {
            "engine": self.ENGINE_VERSION,
            "product_scope": "domain_agnostic_personal_world_anticipation",
            "external_id": external_id,
            "user_found": user is not None if external_id else None,
            "summary": {
                "domains": len(domains),
                "confirmed_events": len(event_rows),
                "emerging_hypotheses": len(candidate_rows),
                "personal_forecasts": len(personal_forecasts),
                "numeric_probabilities_enabled": False,
            },
            "domains": domains,
            "events": event_rows,
            "hypotheses": candidate_rows,
            "personal_forecasts": personal_forecasts,
            "critical_semantics": {
                "weather_social_economic_share_same_prediction_surface": True,
                "unconfirmed_hypothesis_is_fact": False,
                "diagnostic_score_is_probability": False,
                "maturity_is_probability": False,
                "numeric_probabilities_enabled": False,
            },
        }
