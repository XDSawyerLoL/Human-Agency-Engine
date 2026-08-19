from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_impact_schemas import HorizonImpactRequest
from ..horizon_models import HorizonBehaviorPattern, HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_reevaluation_models import HorizonReevaluationDecision
from ..horizon_reevaluation_schemas import HorizonReevaluationRequest
from ..models import Opportunity, PersonalMandate, User
from .horizon import HorizonService
from .horizon_impact import HorizonImpactService
from .horizon_scope import evaluate_personal_scope
from .policy import sha256_dict
from .proactivity import ProactivityService


BAND_RANK = {
    "silent": 0,
    "watch": 1,
    "attention": 2,
    "urgent_attention": 3,
}


class HorizonReevaluationService:
    """Re-evaluate personal impact only when meaningful inputs change.

    The service is deliberately not a broadcast engine. Explicit scope mismatch
    is filtered before impact assessment, unchanged inputs are skipped, and a
    notification is attempted only after a material attention/stage change.
    """

    ENGINE_VERSION = "horizon-auto-reevaluation-v0.1"
    PASSIVE_TIME_BUCKET_SECONDS = 6 * 60 * 60

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _pattern_applies(pattern: HorizonBehaviorPattern, event: HorizonGlobalEvent) -> bool:
        event_types = {str(item) for item in (pattern.event_types or [])}
        return not event_types or "*" in event_types or event.event_type in event_types

    def _input_hash(
        self,
        user: User,
        event: HorizonGlobalEvent,
        pattern: HorizonBehaviorPattern,
        signals: list[HorizonSocialSignal],
        state_snapshot: dict,
        intent_snapshot: list[dict],
        mandate: PersonalMandate | None,
        now: datetime,
    ) -> str:
        # Time is bucketed, not sampled every 15 minutes. This lets urgency be
        # reconsidered as a decision window approaches without creating a new
        # decision on every live-radar poll when nothing else changed.
        time_bucket = int(now.timestamp()) // self.PASSIVE_TIME_BUCKET_SECONDS
        return sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "time_bucket_6h": time_bucket,
                "user": {
                    "id": user.id,
                    "country": user.country,
                    "timezone": user.timezone,
                    "state": state_snapshot,
                    "intents": intent_snapshot,
                    "mandate": {
                        "version": mandate.version if mandate else 0,
                        "constraints": mandate.constraints if mandate else {},
                        "notification_policy": mandate.notification_policy if mandate else {},
                    },
                },
                "event": {
                    "event_key": event.event_key,
                    "event_type": event.event_type,
                    "status": event.status,
                    "geography": event.geography,
                    "source": event.source,
                    "source_reliability": event.source_reliability,
                    "raw_facts": event.raw_facts,
                    "occurred_at": event.occurred_at.isoformat(),
                    "first_observed_at": event.first_observed_at.isoformat(),
                },
                "pattern": {
                    "pattern_key": pattern.pattern_key,
                    "confidence": pattern.confidence,
                    "mechanism_chain": pattern.mechanism_chain,
                    "expected_lag_hours_low": pattern.expected_lag_hours_low,
                    "expected_lag_hours_high": pattern.expected_lag_hours_high,
                    "provenance": pattern.provenance,
                },
                "signals": [
                    {
                        "signal_key": item.signal_key,
                        "signal_type": item.signal_type,
                        "source": item.source,
                        "normalized_score": item.normalized_score,
                        "direction": item.direction,
                        "reliability": item.reliability,
                        "observed_at": item.observed_at.isoformat(),
                    }
                    for item in signals
                ],
            }
        )

    def _latest_surface(
        self, user_id: int, event_id: int, pattern_id: int
    ) -> HorizonReevaluationDecision | None:
        return (
            self.db.query(HorizonReevaluationDecision)
            .filter(
                HorizonReevaluationDecision.user_id == user_id,
                HorizonReevaluationDecision.event_id == event_id,
                HorizonReevaluationDecision.pattern_id == pattern_id,
                HorizonReevaluationDecision.surface_requested == True,  # noqa: E712
            )
            .order_by(HorizonReevaluationDecision.created_at.desc(), HorizonReevaluationDecision.id.desc())
            .first()
        )

    @staticmethod
    def _surface_reason(
        attention_score: float,
        attention_band: str,
        cascade_stage: str,
        previous: HorizonReevaluationDecision | None,
        material_score_delta: float,
    ) -> tuple[bool, str]:
        if BAND_RANK.get(attention_band, 0) < BAND_RANK["attention"]:
            return False, "attention below proactive HORIZON surface band"
        if previous is None:
            return True, "first material personal impact"
        if BAND_RANK.get(attention_band, 0) > BAND_RANK.get(previous.attention_band, 0):
            return True, "attention band increased"
        if (
            cascade_stage
            and cascade_stage != "pre-cascade / latent"
            and cascade_stage != previous.cascade_stage
        ):
            return True, "collective behavior advanced to a new sequential stage"
        if attention_score >= float(previous.attention_score) + material_score_delta:
            return True, f"attention score increased by at least {material_score_delta:.2f}"
        return False, "no material change since the last surfaced HORIZON state"

    def _find_or_create_opportunity(
        self,
        decision: HorizonReevaluationDecision,
        user: User,
        event: HorizonGlobalEvent,
        pattern: HorizonBehaviorPattern,
        assessment,
    ) -> Opportunity:
        if decision.opportunity_id is not None:
            existing = self.db.query(Opportunity).filter(Opportunity.id == decision.opportunity_id).one_or_none()
            if existing is not None:
                return existing

        category = f"horizon_{event.event_type}"[:64]
        # Recovery path for a process interruption after Opportunity commit but
        # before the decision row was linked. No database-specific JSON operator
        # is required; only a small recent category slice is inspected.
        recent = (
            self.db.query(Opportunity)
            .filter(Opportunity.user_id == user.id, Opportunity.category == category)
            .order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
            .limit(20)
            .all()
        )
        for item in recent:
            payload = item.proposed_action if isinstance(item.proposed_action, dict) else {}
            if payload.get("horizon_decision_id") == decision.id:
                decision.opportunity_id = item.id
                self.db.commit()
                return item

        collective = assessment.collective_behavior_layer or {}
        scope = (assessment.personal_exposure_layer or {}).get("personal_scope", {})
        rationale = (
            f"Confirmed information: {event.title}. Source: {event.source}. "
            f"HORIZON's behavioral model is currently at '{collective.get('current_stage', 'unknown')}'. "
            f"Personal relevance is '{assessment.attention_band}' with scope '{scope.get('status', 'unscoped')}'. "
            "The attention score is a prioritization diagnostic, not a probability, and no action is prescribed."
        )
        evidence_confidence = max(
            0.0,
            min(1.0, (float(event.source_reliability) + float(pattern.confidence)) / 2.0),
        )
        opportunity = Opportunity(
            user_id=user.id,
            signal_id=None,
            category=category,
            title=f"HORIZON · {event.title}"[:255],
            rationale=rationale,
            proposed_action={
                "type": "review_horizon_alert",
                "horizon_decision_id": decision.id,
                "event_id": event.id,
                "pattern_id": pattern.id,
                "assessment_id": assessment.id,
                "raw_information": assessment.fact_layer,
                "collective_behavior": assessment.collective_behavior_layer,
                "personal_exposure": assessment.personal_exposure_layer,
                "timing": assessment.timing_layer,
                "attention_score": assessment.attention_score,
                "attention_score_is_probability": False,
                "action_prescribed": False,
            },
            baseline={"state": "no_notification"},
            counterfactual={"state": "user_reviews_raw_information_and_inference"},
            expected_value=0.0,
            confidence=round(evidence_confidence, 4),
            care_status="approved",
            care_reason="HORIZON information-only alert; no external action is authorized",
            status="open",
        )
        self.db.add(opportunity)
        self.db.commit()
        self.db.refresh(opportunity)
        decision.opportunity_id = opportunity.id
        decision.updated_at = datetime.utcnow()
        self.db.commit()
        return opportunity

    def _surface(
        self,
        decision: HorizonReevaluationDecision,
        user: User,
        event: HorizonGlobalEvent,
        pattern: HorizonBehaviorPattern,
        assessment,
    ) -> str:
        opportunity = self._find_or_create_opportunity(decision, user, event, pattern, assessment)
        notification = ProactivityService(self.db).evaluate_horizon(
            user,
            opportunity,
            attention_score=float(assessment.attention_score),
        )
        decision.notification_id = notification.id
        decision.status = notification.status
        decision.reason = notification.suppression_reason or decision.reason
        decision.updated_at = datetime.utcnow()
        self.db.commit()
        return notification.status

    def run(self, request: HorizonReevaluationRequest) -> dict:
        now = datetime.utcnow()
        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(HorizonGlobalEvent.status == "active", HorizonGlobalEvent.first_observed_at <= now)
            .order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
            .limit(request.max_events)
            .all()
        )
        patterns = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= now,
            )
            .order_by(HorizonBehaviorPattern.id.asc())
            .all()
        )
        users = self.db.query(User).order_by(User.id.asc()).limit(request.max_users).all()
        horizon = HorizonService(self.db)

        totals = {
            "events_scanned": len(events),
            "users_available": len(users),
            "event_pattern_pairs": 0,
            "user_pairs_scanned": 0,
            "scope_mismatches": 0,
            "unchanged_inputs": 0,
            "assessments": 0,
            "silent_decisions": 0,
            "surface_requested": 0,
            "queued_notifications": 0,
            "suppressed_notifications": 0,
            "resumed_decisions": 0,
            "errors": [],
        }

        for event in events:
            event_patterns = [item for item in patterns if self._pattern_applies(item, event)]
            for pattern in event_patterns:
                totals["event_pattern_pairs"] += 1
                signals = (
                    self.db.query(HorizonSocialSignal)
                    .filter(HorizonSocialSignal.event_id == event.id, HorizonSocialSignal.observed_at <= now)
                    .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
                    .all()
                )
                for user in users:
                    totals["user_pairs_scanned"] += 1
                    try:
                        state_snapshot = horizon._state_as_of(user, now)
                        intent_snapshot = horizon._intents_as_of(user, now)
                        mandate = (
                            self.db.query(PersonalMandate)
                            .filter(PersonalMandate.user_id == user.id)
                            .one_or_none()
                        )
                        input_hash = self._input_hash(
                            user,
                            event,
                            pattern,
                            signals,
                            state_snapshot,
                            intent_snapshot,
                            mandate,
                            now,
                        )
                        decision_key = sha256_dict(
                            {
                                "engine": self.ENGINE_VERSION,
                                "user_id": user.id,
                                "event_id": event.id,
                                "pattern_id": pattern.id,
                                "input_hash": input_hash,
                            }
                        )
                        existing = (
                            self.db.query(HorizonReevaluationDecision)
                            .filter(HorizonReevaluationDecision.decision_key == decision_key)
                            .one_or_none()
                        )
                        if existing is not None:
                            if existing.status == "processing" and existing.surface_requested:
                                assessment = existing.assessment_id and self.db.query(
                                    __import__("app.horizon_impact_models", fromlist=["HorizonPersonalImpactAssessment"]).HorizonPersonalImpactAssessment
                                ).filter_by(id=existing.assessment_id).one_or_none()
                                if assessment is not None:
                                    status = self._surface(existing, user, event, pattern, assessment)
                                    totals["resumed_decisions"] += 1
                                    totals["queued_notifications"] += int(status == "queued")
                                    totals["suppressed_notifications"] += int(status == "suppressed")
                                    continue
                            totals["unchanged_inputs"] += 1
                            continue

                        personal_scope = (event.raw_facts or {}).get("personal_scope")
                        scope = evaluate_personal_scope(state_snapshot, personal_scope)
                        if scope["configured"] and scope["status"] == "mismatched":
                            self.db.add(
                                HorizonReevaluationDecision(
                                    decision_key=decision_key,
                                    input_hash=input_hash,
                                    user_id=user.id,
                                    event_id=event.id,
                                    pattern_id=pattern.id,
                                    scope_status="mismatched",
                                    attention_score=0.0,
                                    attention_band="silent",
                                    cascade_stage="",
                                    surface_requested=False,
                                    status="scope_mismatch",
                                    reason="explicit personal scope mismatch; impact assessment skipped",
                                )
                            )
                            self.db.commit()
                            totals["scope_mismatches"] += 1
                            continue

                        assessment = HorizonImpactService(self.db).assess(
                            user,
                            HorizonImpactRequest(
                                event_id=event.id,
                                pattern_id=pattern.id,
                                as_of=now,
                                mode="live",
                            ),
                        )
                        totals["assessments"] += 1
                        exposure = assessment.personal_exposure_layer or {}
                        scope_status = (exposure.get("personal_scope") or {}).get("status", "unscoped")
                        stage = str((assessment.collective_behavior_layer or {}).get("current_stage") or "")
                        previous = self._latest_surface(user.id, event.id, pattern.id)
                        should_surface, reason = self._surface_reason(
                            float(assessment.attention_score),
                            assessment.attention_band,
                            stage,
                            previous,
                            request.material_score_delta,
                        )
                        decision = HorizonReevaluationDecision(
                            decision_key=decision_key,
                            input_hash=input_hash,
                            user_id=user.id,
                            event_id=event.id,
                            pattern_id=pattern.id,
                            assessment_id=assessment.id,
                            scope_status=scope_status,
                            attention_score=float(assessment.attention_score),
                            attention_band=assessment.attention_band,
                            cascade_stage=stage,
                            surface_requested=should_surface,
                            status="processing" if should_surface else "silent",
                            reason=reason,
                        )
                        self.db.add(decision)
                        self.db.commit()
                        self.db.refresh(decision)

                        if not should_surface:
                            totals["silent_decisions"] += 1
                            continue

                        totals["surface_requested"] += 1
                        status = self._surface(decision, user, event, pattern, assessment)
                        totals["queued_notifications"] += int(status == "queued")
                        totals["suppressed_notifications"] += int(status == "suppressed")
                    except Exception as exc:
                        self.db.rollback()
                        if len(totals["errors"]) < 25:
                            totals["errors"].append(
                                {
                                    "user_id": user.id,
                                    "event_id": event.id,
                                    "pattern_id": pattern.id,
                                    "error": str(exc)[:300],
                                }
                            )

        totals["errors_count"] = len(totals["errors"])
        totals["external_action_executed"] = False
        totals["attention_score_is_probability"] = False
        return totals
