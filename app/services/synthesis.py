from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..future_schemas import FutureCompareRequest, FutureScenarioInput
from ..models import Intent, Opportunity, User
from ..synthesis_models import CandidateIntervention
from ..world_models import WorldHypothesis
from ..world_schemas import EventCreate
from .decision_lab import DecisionLab
from .future import FutureEngine
from .intent_matcher import best_intent_match
from .proactivity import ProactivityService
from .world_model import WorldModelService

READY_STATUSES = {
    "strong_candidate_for_user_review",
    "candidate_for_reversible_pilot",
}
REJECT_STATUSES = {"do_not_act", "do_not_prefer"}


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _key(source_type: str, source_ref: str, intervention: dict, effects: dict) -> str:
    raw = _canonical(
        {
            "source_type": source_type,
            "source_ref": source_ref,
            "intervention": intervention,
            "effects": effects,
        }
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SynthesisService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, user: User, *, horizon_days: int = 90, limit: int = 10) -> dict:
        generated = self._generate_candidates(user, horizon_days=horizon_days)
        pending = (
            self.db.query(CandidateIntervention)
            .filter(
                CandidateIntervention.user_id == user.id,
                CandidateIntervention.status == "generated",
            )
            .order_by(CandidateIntervention.confidence.desc(), CandidateIntervention.created_at.asc())
            .limit(max(1, min(limit, 10)))
            .all()
        )

        if not pending:
            return {
                "generated": generated,
                "evaluated": 0,
                "ready_for_review": 0,
                "needs_information": 0,
                "rejected": 0,
                "queued_notifications": 0,
                "suppressed_notifications": 0,
                "future_run_id": None,
            }

        scenario_inputs: list[FutureScenarioInput] = []
        valid_candidates: list[CandidateIntervention] = []
        for candidate in pending:
            intervention = dict(candidate.intervention)
            intervention["_candidate_id"] = candidate.id
            try:
                scenario = FutureScenarioInput(
                    name=candidate.name,
                    intervention=intervention,
                    effects=candidate.effects,
                    assumptions=candidate.assumptions,
                    evidence=candidate.evidence,
                )
            except ValidationError as exc:
                candidate.status = "needs_information"
                candidate.rejection_reason = f"effect/assumption model is structurally invalid: {exc.errors()[0]['msg']}"
                candidate.updated_at = datetime.utcnow()
                continue
            scenario_inputs.append(scenario)
            valid_candidates.append(candidate)

        self.db.commit()
        if not scenario_inputs:
            return {
                "generated": generated,
                "evaluated": 0,
                "ready_for_review": 0,
                "needs_information": len(pending),
                "rejected": 0,
                "queued_notifications": 0,
                "suppressed_notifications": 0,
                "future_run_id": None,
            }

        run, scenarios = FutureEngine(self.db).compare(
            user,
            FutureCompareRequest(
                horizon_days=horizon_days,
                objective="Evaluate synthesized interventions before they may reach user attention.",
                scenarios=scenario_inputs,
            ),
        )
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="synthesis.future_gate_created",
                source="synthesis_engine",
                subject_type="future_run",
                subject_id=str(run.id),
                payload={"candidate_ids": [item.id for item in valid_candidates]},
                correlation_id=f"synthesis-run:{run.id}",
            ),
        )

        decision = DecisionLab(self.db).analyze(run)
        analysis_by_scenario = {
            item["scenario_id"]: item for item in decision["scenario_analysis"]
        }
        scenario_by_candidate: dict[int, object] = {}
        for scenario in scenarios:
            if scenario.scenario_type == "baseline":
                continue
            candidate_id = scenario.intervention.get("_candidate_id")
            if isinstance(candidate_id, int):
                scenario_by_candidate[candidate_id] = scenario

        ready = 0
        needs_information = 0
        rejected = 0
        queued = 0
        suppressed = 0
        baseline = next(item for item in scenarios if item.scenario_type == "baseline")
        proactivity = ProactivityService(self.db)
        world = WorldModelService(self.db)

        for candidate in valid_candidates:
            scenario = scenario_by_candidate.get(candidate.id)
            if scenario is None:
                candidate.status = "needs_information"
                candidate.rejection_reason = "scenario mapping missing after FUTURE run"
                needs_information += 1
                continue
            analysis = analysis_by_scenario.get(scenario.id, {})
            decision_status = str(analysis.get("decision_status", "insufficient_information"))
            candidate.future_run_id = run.id
            candidate.scenario_id = scenario.id
            candidate.decision_status = decision_status
            candidate.updated_at = datetime.utcnow()

            if decision_status in READY_STATUSES:
                candidate.status = "ready_for_review"
                candidate.rejection_reason = ""
                ready += 1
                surfaced = self._surface_candidate(user, candidate, baseline, scenario)
                notification = proactivity.evaluate(user, surfaced)
                queued += int(notification.status == "queued")
                suppressed += int(notification.status == "suppressed")
            elif decision_status in REJECT_STATUSES:
                candidate.status = "rejected"
                candidate.rejection_reason = decision_status
                rejected += 1
            else:
                candidate.status = "needs_information"
                candidate.rejection_reason = decision_status
                needs_information += 1

            world.append_event(
                user,
                EventCreate(
                    event_type="candidate.evaluated",
                    source="decision_lab",
                    subject_type="candidate_intervention",
                    subject_id=str(candidate.id),
                    payload={
                        "status": candidate.status,
                        "decision_status": candidate.decision_status,
                        "future_run_id": candidate.future_run_id,
                        "scenario_id": candidate.scenario_id,
                    },
                    confidence=float(scenario.confidence),
                    correlation_id=f"synthesis-run:{run.id}",
                ),
                commit=False,
            )

        self.db.commit()
        world.append_event(
            user,
            EventCreate(
                event_type="synthesis.run_completed",
                source="synthesis_engine",
                subject_type="synthesis_run",
                subject_id=str(run.id),
                payload={
                    "evaluated": len(valid_candidates),
                    "ready_for_review": ready,
                    "needs_information": needs_information,
                    "rejected": rejected,
                    "queued_notifications": queued,
                    "suppressed_notifications": suppressed,
                },
                correlation_id=f"synthesis-run:{run.id}",
            ),
        )
        return {
            "generated": generated,
            "evaluated": len(valid_candidates),
            "ready_for_review": ready,
            "needs_information": needs_information,
            "rejected": rejected,
            "queued_notifications": queued,
            "suppressed_notifications": suppressed,
            "future_run_id": run.id,
        }

    def _generate_candidates(self, user: User, *, horizon_days: int) -> int:
        active_intents = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.active == True)  # noqa: E712
            .all()
        )
        specs: list[dict] = []
        raw_opportunities = (
            self.db.query(Opportunity)
            .filter(
                Opportunity.user_id == user.id,
                Opportunity.status == "open",
                Opportunity.category != "synthesized",
            )
            .order_by(Opportunity.created_at.asc())
            .all()
        )
        for opportunity in raw_opportunities:
            spec = self._from_opportunity(user, opportunity, active_intents, horizon_days)
            if spec:
                specs.append(spec)

        hypotheses = (
            self.db.query(WorldHypothesis)
            .filter(
                WorldHypothesis.user_id == user.id,
                WorldHypothesis.status == "active",
                WorldHypothesis.claim_level == "personal_empirical",
            )
            .all()
        )
        for hypothesis in hypotheses:
            spec = self._from_hypothesis(hypothesis, active_intents)
            if spec:
                specs.append(spec)

        created = 0
        for spec in specs:
            candidate_key = _key(
                spec["source_type"],
                spec["source_ref"],
                spec["intervention"],
                spec["effects"],
            )
            existing = (
                self.db.query(CandidateIntervention)
                .filter(
                    CandidateIntervention.user_id == user.id,
                    CandidateIntervention.candidate_key == candidate_key,
                )
                .one_or_none()
            )
            if existing:
                continue
            candidate = CandidateIntervention(
                user_id=user.id,
                candidate_key=candidate_key,
                **spec,
            )
            self.db.add(candidate)
            created += 1
        self.db.commit()
        return created

    def _from_opportunity(
        self,
        user: User,
        opportunity: Opportunity,
        intents: list[Intent],
        horizon_days: int,
    ) -> dict | None:
        text = f"{opportunity.title} {opportunity.rationale} {_canonical(opportunity.proposed_action)}"
        intent, match_score = best_intent_match(text, intents)
        intent_ids = [intent.id] if intent is not None and match_score >= 0.15 else []
        if not intent_ids and opportunity.category not in {"money", "risk", "timing"}:
            return None

        intervention = dict(opportunity.proposed_action or {})
        effects: dict = {}
        assumptions: list[dict] = []
        action_type = str(intervention.get("type", ""))

        if action_type == "review_subscription":
            amount = intervention.get("monthly_amount")
            if isinstance(amount, (int, float)) and amount > 0:
                maximum = round(float(amount) * (horizon_days / 30.4375), 4)
                effects["cash_balance"] = {
                    "low": 0.0,
                    "central": maximum,
                    "high": maximum,
                    "unit": user.currency,
                    "direction": "higher_is_better",
                    "rationale": "mechanical avoided subscription cost over the simulation horizon if cancellation is appropriate",
                }
                assumptions.append(
                    {
                        "statement": "the subscription can be reduced or cancelled without losing value the user still needs",
                        "confidence": min(float(opportunity.confidence), 0.6),
                        "source": f"opportunity:{opportunity.id}",
                        "falsifiable_by": "verify actual use, cancellation terms and replacement need",
                    }
                )
        elif action_type == "consider_purchase":
            savings = opportunity.counterfactual.get("savings_vs_reference") if isinstance(opportunity.counterfactual, dict) else None
            if isinstance(savings, (int, float)) and savings > 0:
                effects["purchase_cost_avoided"] = {
                    "low": 0.0,
                    "central": float(savings),
                    "high": float(savings),
                    "unit": user.currency,
                    "direction": "higher_is_better",
                    "rationale": "difference versus the recorded reference price, conditional on the purchase being needed anyway",
                }
                assumptions.append(
                    {
                        "statement": "the user would otherwise make the same purchase later near the reference price",
                        "confidence": min(float(opportunity.confidence), 0.55),
                        "source": f"opportunity:{opportunity.id}",
                        "falsifiable_by": "confirm the purchase remains intended and compare current alternatives",
                    }
                )

        if not assumptions:
            assumptions.append(
                {
                    "statement": "the detected opportunity is still relevant to the user's current context",
                    "confidence": min(float(opportunity.confidence), 0.65),
                    "source": f"opportunity:{opportunity.id}",
                    "falsifiable_by": "verify the triggering signal and current intent before acting",
                }
            )

        return {
            "source_type": "opportunity",
            "source_ref": str(opportunity.id),
            "source_opportunity_id": opportunity.id,
            "hypothesis_ids": [],
            "intent_ids": intent_ids,
            "name": opportunity.title,
            "rationale": opportunity.rationale,
            "intervention": intervention,
            "effects": effects,
            "assumptions": assumptions,
            "evidence": {
                "level": "observational",
                "sources": [f"opportunity:{opportunity.id}", f"signal:{opportunity.signal_id}" if opportunity.signal_id else ""],
                "notes": "candidate derived from observed signal/opportunity; not causal evidence",
            },
            "confidence": float(opportunity.confidence),
        }

    def _from_hypothesis(self, hypothesis: WorldHypothesis, intents: list[Intent]) -> dict | None:
        intervention = hypothesis.cause_pattern.get("intervention") if isinstance(hypothesis.cause_pattern, dict) else None
        metrics = hypothesis.effect_pattern.get("metrics") if isinstance(hypothesis.effect_pattern, dict) else None
        if not isinstance(intervention, dict) or not intervention:
            return None
        if not isinstance(metrics, dict):
            metrics = {}

        text = f"{hypothesis.name} {_canonical(hypothesis.cause_pattern)} {_canonical(hypothesis.effect_pattern)}"
        intent, match_score = best_intent_match(text, intents)
        if intents and (intent is None or match_score < 0.15):
            return None
        intent_ids = [intent.id] if intent is not None else []

        return {
            "source_type": "hypothesis",
            "source_ref": str(hypothesis.id),
            "source_opportunity_id": None,
            "hypothesis_ids": [hypothesis.id],
            "intent_ids": intent_ids,
            "name": hypothesis.name,
            "rationale": "intervention candidate derived from repeated personal evidence; FUTURE and Decision Lab must still gate it",
            "intervention": intervention,
            "effects": metrics,
            "assumptions": [
                {
                    "statement": "the repeated personal pattern remains applicable in the current context",
                    "confidence": float(hypothesis.confidence),
                    "source": f"world_hypothesis:{hypothesis.id}",
                    "falsifiable_by": str(hypothesis.context.get("falsifiable_by", "compare current context with prior experiments")) if isinstance(hypothesis.context, dict) else "compare current context with prior experiments",
                }
            ],
            "evidence": {
                "level": "personal_repeated",
                "sources": [f"world_hypothesis:{hypothesis.id}"],
                "notes": "personal repeated evidence; not automatically general causal evidence",
            },
            "confidence": float(hypothesis.confidence),
        }

    def _surface_candidate(self, user: User, candidate: CandidateIntervention, baseline, scenario) -> Opportunity:
        if candidate.surfaced_opportunity_id is not None:
            existing = (
                self.db.query(Opportunity)
                .filter(Opportunity.id == candidate.surfaced_opportunity_id)
                .one_or_none()
            )
            if existing:
                return existing

        proposed_action = dict(candidate.intervention)
        proposed_action.pop("_candidate_id", None)
        opportunity = Opportunity(
            user_id=user.id,
            signal_id=None,
            category="synthesized",
            title=candidate.name,
            rationale=(
                candidate.rationale
                + f" Decision gate: {candidate.decision_status}. This is a candidate for review, not authorization."
            ),
            proposed_action=proposed_action,
            baseline=baseline.projected_metrics,
            counterfactual=scenario.projected_metrics,
            expected_value=0.0,
            confidence=float(scenario.confidence),
            care_status="approved",
            care_reason="passed FUTURE + Decision Lab gate; execution still requires user authorization",
            status="open",
        )
        self.db.add(opportunity)
        self.db.flush()
        candidate.surfaced_opportunity_id = opportunity.id
        return opportunity
