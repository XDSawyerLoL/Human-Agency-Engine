from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_cascade_schemas import HorizonCascadeRequest
from ..horizon_impact_models import HorizonPersonalImpactAssessment
from ..horizon_impact_schemas import HorizonImpactRequest
from ..horizon_models import HorizonBehaviorPattern, HorizonForecast, HorizonGlobalEvent
from ..models import User
from .horizon import HorizonService
from .horizon_cascade import HorizonCascadeService
from .horizon_scope import evaluate_personal_scope
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _attention_band(score: float) -> str:
    if score >= 0.76:
        return "urgent_attention"
    if score >= 0.58:
        return "attention"
    if score >= 0.40:
        return "watch"
    return "silent"


class HorizonImpactService:
    ENGINE_VERSION = "horizon-personal-impact-gate-v0.2-scope"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _urgency(as_of: datetime, onset_low: datetime, onset_high: datetime) -> tuple[float, dict]:
        if onset_high < as_of:
            return 0.0, {
                "status": "likely_closed",
                "expected_onset_low": onset_low.isoformat(),
                "expected_onset_high": onset_high.isoformat(),
                "hours_to_earliest_onset": None,
            }
        hours = (onset_low - as_of).total_seconds() / 3600.0
        if hours <= 0:
            urgency = 0.90
            status = "active_or_closing"
        elif hours <= 24:
            urgency = 0.85
            status = "open_near_term"
        elif hours <= 72:
            urgency = 0.70
            status = "open_short_term"
        elif hours <= 168:
            urgency = 0.50
            status = "open_this_week"
        else:
            urgency = 0.25
            status = "open_later"
        return urgency, {
            "status": status,
            "expected_onset_low": onset_low.isoformat(),
            "expected_onset_high": onset_high.isoformat(),
            "hours_to_earliest_onset": round(max(hours, 0.0), 2),
        }

    def assess(self, user: User, request: HorizonImpactRequest) -> HorizonPersonalImpactAssessment:
        now = datetime.utcnow()
        as_of = _utc_naive(request.as_of) if request.as_of else now
        if request.mode == "live" and as_of > now + timedelta(minutes=5):
            raise ValueError("live impact assessment as_of cannot be in the future")

        event = self.db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id == request.event_id,
            HorizonGlobalEvent.status == "active",
        ).one_or_none()
        if event is None:
            raise ValueError("HORIZON event not found")
        if event.first_observed_at > as_of:
            raise ValueError("event was not observable at the requested cutoff")

        pattern = self.db.query(HorizonBehaviorPattern).filter(
            HorizonBehaviorPattern.id == request.pattern_id,
            HorizonBehaviorPattern.status == "active",
            HorizonBehaviorPattern.knowledge_available_at <= as_of,
        ).one_or_none()
        if pattern is None:
            raise ValueError("behavior pattern was not available at the requested cutoff")

        cascade = HorizonCascadeService(self.db).project(HorizonCascadeRequest(
            event_id=event.id,
            pattern_id=pattern.id,
            as_of=as_of,
            mode=request.mode,
        ))
        horizon = HorizonService(self.db)
        exposure = horizon._personal_exposure(user, event, as_of)

        personal_scope = (event.raw_facts or {}).get("personal_scope")
        scope = evaluate_personal_scope(exposure.get("state_snapshot", {}), personal_scope)
        base_exposure_score = _clamp(float(exposure["score"]))
        if scope["configured"]:
            if scope["status"] == "matched":
                scoped_exposure_score = _clamp(0.55 + 0.45 * base_exposure_score)
            elif scope["status"] == "mismatched":
                scoped_exposure_score = min(base_exposure_score, 0.05)
            else:
                scoped_exposure_score = min(base_exposure_score, 0.25)
            exposure["unscoped_score"] = round(base_exposure_score, 4)
            exposure["score"] = round(scoped_exposure_score, 4)
            exposure["personal_scope"] = scope
        else:
            scoped_exposure_score = base_exposure_score
            exposure["personal_scope"] = scope

        source_quality = _clamp(event.source_reliability)
        pattern_quality = _clamp(pattern.confidence)
        exposure_score = _clamp(scoped_exposure_score)
        propagation = _clamp(cascade.propagation_score)
        acceleration = _clamp(cascade.acceleration_score)

        impact_score = _clamp(
            0.22 * source_quality
            + 0.18 * pattern_quality
            + 0.32 * exposure_score
            + 0.28 * propagation
        )
        onset_low = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_low)
        onset_high = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_high)
        urgency_score, timing = self._urgency(as_of, onset_low, onset_high)
        attention_score = _clamp(
            0.62 * impact_score
            + 0.23 * urgency_score
            + 0.15 * acceleration
        )

        # Explicit personal scope is a hard relevance gate. A known mismatch must
        # never leak a high-severity regional alert to the wrong human. Missing
        # personal state may justify a watch/data-acquisition prompt, never urgency.
        if scope["configured"] and scope["status"] == "mismatched":
            attention_score = 0.0
        elif scope["configured"] and scope["status"] == "unknown":
            attention_score = min(attention_score, 0.49)
        band = _attention_band(attention_score)

        forecast = self.db.query(HorizonForecast).filter(
            HorizonForecast.user_id == user.id,
            HorizonForecast.event_id == event.id,
            HorizonForecast.pattern_id == pattern.id,
            HorizonForecast.mode == request.mode,
            HorizonForecast.as_of == as_of,
        ).one_or_none()

        key = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "user_id": user.id,
            "event_id": event.id,
            "pattern_id": pattern.id,
            "cascade_key": cascade.cascade_key,
            "mode": request.mode,
            "as_of": as_of.isoformat(),
        })
        existing = self.db.query(HorizonPersonalImpactAssessment).filter(
            HorizonPersonalImpactAssessment.assessment_key == key
        ).one_or_none()
        if existing:
            return existing

        fact_layer = {
            "event_key": event.event_key,
            "event_type": event.event_type,
            "title": event.title,
            "summary": event.summary,
            "geography": event.geography,
            "source": event.source,
            "source_url": event.source_url,
            "source_reliability": event.source_reliability,
            "raw_facts": event.raw_facts,
            "occurred_at": event.occurred_at.isoformat(),
            "first_observed_at": event.first_observed_at.isoformat(),
        }
        collective_layer = {
            "current_stage": cascade.current_stage,
            "next_stage": cascade.next_stage or None,
            "stages": cascade.stage_snapshot,
            "propagation_score": cascade.propagation_score,
            "acceleration_score": cascade.acceleration_score,
            "evidence_diversity_score": cascade.evidence_diversity_score,
            "confidence_band": cascade.confidence_band,
            "probability_basis": cascade.probability_basis,
            "interpretation": cascade.interpretation,
        }
        explanation = {
            "raw_information_available": True,
            "fact_and_inference_separated": True,
            "attention_score_is_probability": False,
            "formal_probability_enabled": False,
            "action_prescribed": False,
            "should_surface": band != "silent",
            "personal_scope_status": scope["status"],
            "personal_scope_configured": scope["configured"],
            "missing_personal_state_for_scope": scope["configured"] and scope["status"] == "unknown",
            "why": [
                {"component": "event_source_quality", "score": round(source_quality, 4)},
                {"component": "historical_pattern_support", "score": round(pattern_quality, 4)},
                {"component": "personal_exposure", "score": round(exposure_score, 4)},
                {"component": "personal_scope", "score": round(float(scope["score"]), 4)},
                {"component": "collective_cascade_progress", "score": round(propagation, 4)},
                {"component": "collective_cascade_acceleration", "score": round(acceleration, 4)},
            ],
            "human_readable": (
                f"The event is personally relevant at attention band '{band}'. "
                f"Personal scope is '{scope['status']}'. "
                f"Collective behavior is currently '{cascade.current_stage}', "
                f"with next plausible transition '{cascade.next_stage or 'none'}'."
            ),
        }

        row = HorizonPersonalImpactAssessment(
            assessment_key=key,
            user_id=user.id,
            event_id=event.id,
            pattern_id=pattern.id,
            forecast_id=forecast.id if forecast else None,
            cascade_id=cascade.id,
            mode=request.mode,
            as_of=as_of,
            fact_layer=fact_layer,
            collective_behavior_layer=collective_layer,
            personal_exposure_layer=exposure,
            timing_layer=timing,
            impact_score=round(impact_score, 4),
            urgency_score=round(urgency_score, 4),
            attention_score=round(attention_score, 4),
            attention_band=band,
            explanation=explanation,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
