from __future__ import annotations

import hashlib
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..acquisition_models import InformationNeed
from ..acquisition_schemas import InformationResolution
from ..models import FutureRun, PersonalMandate, StateFact, User
from ..synthesis_models import CandidateIntervention
from ..world_schemas import EventCreate
from .decision_lab import DecisionLab
from .world_model import WorldModelService

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
FINANCIAL_UNKNOWN_FIELDS = {"monthly_income", "monthly_fixed_costs", "liquid_cash"}


def _need_key(candidate_id: int, future_run_id: int, need_type: str, question: str) -> str:
    material = f"{candidate_id}|{future_run_id}|{need_type}|{question}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _source_policy(need_type: str, question: str) -> tuple[str, list[str], str]:
    lower = question.lower()
    sensitivity = (
        "sensitive"
        if any(term in lower for term in ("income", "cash", "cost", "financial", "salary"))
        else "personal"
    )
    if need_type == "reduce_sign_uncertainty":
        return (
            "experiment_then_user",
            ["world_experiments", "reversible_pilot", "user"],
            sensitivity,
        )
    if need_type == "check_reversibility":
        return (
            "read_only_then_user",
            ["source_terms", "connected_read_only_sources", "user"],
            sensitivity,
        )
    if need_type == "resolve_missing_state":
        return (
            "read_only_then_user",
            ["self_graph", "connected_read_only_sources", "user"],
            sensitivity,
        )
    return (
        "read_only_then_user",
        ["self_graph", "world_events", "connected_read_only_sources", "user"],
        sensitivity,
    )


class InformationAcquisitionService:
    """Turn epistemic uncertainty into explicit, bounded information work.

    The service never invents a missing value. It first tries already-authorized state,
    then makes unresolved needs available to an attention-budgeted user question queue.
    Resolutions can update the candidate model and only then requeue it through FUTURE.
    """

    def __init__(self, db: Session):
        self.db = db

    def materialize(self, user: User) -> dict:
        candidates = (
            self.db.query(CandidateIntervention)
            .filter(
                CandidateIntervention.user_id == user.id,
                CandidateIntervention.status == "needs_information",
                CandidateIntervention.future_run_id.is_not(None),
                CandidateIntervention.scenario_id.is_not(None),
            )
            .all()
        )
        created = 0
        runs: dict[int, dict] = {}
        world = WorldModelService(self.db)

        for candidate in candidates:
            run_id = int(candidate.future_run_id)
            if run_id not in runs:
                run = self.db.query(FutureRun).filter(FutureRun.id == run_id).one_or_none()
                if not run:
                    continue
                runs[run_id] = DecisionLab(self.db).analyze(run)
            analysis = next(
                (
                    item
                    for item in runs[run_id]["scenario_analysis"]
                    if item["scenario_id"] == candidate.scenario_id
                ),
                None,
            )
            if analysis is None:
                continue
            actions = list(analysis.get("information_actions", []))
            if not actions:
                actions = [
                    {
                        "type": "model_effects",
                        "scenario_id": candidate.scenario_id,
                        "question": (
                            "Establish bounded low/central/high effects before this "
                            "intervention can be compared responsibly"
                        ),
                        "reason": candidate.decision_status or "effect model is incomplete",
                        "priority": "high",
                    }
                ]

            for action in actions:
                question = str(action.get("question", "")).strip()
                need_type = str(action.get("type", "verify_assumption"))
                if not question:
                    continue
                key = _need_key(candidate.id, run_id, need_type, question)
                existing = (
                    self.db.query(InformationNeed)
                    .filter(
                        InformationNeed.user_id == user.id,
                        InformationNeed.need_key == key,
                    )
                    .one_or_none()
                )
                if existing:
                    continue
                mode, sources, sensitivity = _source_policy(need_type, question)
                need = InformationNeed(
                    user_id=user.id,
                    candidate_id=candidate.id,
                    future_run_id=run_id,
                    scenario_id=candidate.scenario_id,
                    need_key=key,
                    need_type=need_type,
                    question=question,
                    reason=str(action.get("reason", "")),
                    priority=str(action.get("priority", "medium")),
                    acquisition_mode=mode,
                    preferred_sources=sources,
                    sensitivity=sensitivity,
                    blocks_candidate=True,
                )
                self.db.add(need)
                self.db.flush()
                created += 1
                world.append_event(
                    user,
                    EventCreate(
                        event_type="information.need_created",
                        source="decision_lab",
                        subject_type="information_need",
                        subject_id=str(need.id),
                        payload={
                            "candidate_id": candidate.id,
                            "future_run_id": run_id,
                            "need_type": need.need_type,
                            "priority": need.priority,
                            "acquisition_mode": need.acquisition_mode,
                            "sensitivity": need.sensitivity,
                        },
                        correlation_id=f"candidate:{candidate.id}",
                    ),
                    commit=False,
                )

        self.db.commit()
        auto = self.auto_resolve_from_known_state(user)
        return {
            "candidates_scanned": len(candidates),
            "needs_created": created,
            "auto_resolved": auto,
            "open_needs": self._open_count(user),
        }

    def auto_resolve_from_known_state(self, user: User) -> int:
        needs = (
            self.db.query(InformationNeed)
            .filter(
                InformationNeed.user_id == user.id,
                InformationNeed.status == "open",
                InformationNeed.need_type == "resolve_missing_state",
            )
            .all()
        )
        resolved = 0
        for need in needs:
            unknown = need.question.split(":", 1)[-1].strip()
            if unknown in FINANCIAL_UNKNOWN_FIELDS:
                value = getattr(user, unknown, None)
                if value is not None:
                    self.resolve(
                        user,
                        need,
                        InformationResolution(
                            value={"field": unknown, "value": value},
                            source="self_graph",
                            provenance={"user_field": unknown},
                            confidence=1.0,
                        ),
                        allow_state_update=False,
                    )
                    resolved += 1
            elif unknown == "no temporal state facts":
                has_fact = (
                    self.db.query(StateFact)
                    .filter(
                        StateFact.user_id == user.id,
                        StateFact.superseded == False,  # noqa: E712
                    )
                    .first()
                    is not None
                )
                if has_fact:
                    self.resolve(
                        user,
                        need,
                        InformationResolution(
                            value={"state_fact_exists": True},
                            source="self_graph",
                            provenance={"query": "active state fact exists"},
                            confidence=1.0,
                        ),
                        allow_state_update=False,
                    )
                    resolved += 1
        return resolved

    def resolve(
        self,
        user: User,
        need: InformationNeed,
        payload: InformationResolution,
        *,
        allow_state_update: bool = True,
    ) -> InformationNeed:
        if need.user_id != user.id:
            raise ValueError("information need does not belong to user")
        if need.status == "resolved":
            raise ValueError("information need is already resolved")
        if payload.source == "inference" and need.sensitivity == "sensitive":
            raise ValueError("sensitive information cannot be resolved from unverified inference")

        need.status = "resolved"
        need.resolution = payload.value
        need.resolution_source = payload.source
        need.resolution_provenance = payload.provenance
        need.resolution_confidence = payload.confidence
        need.resolved_at = datetime.utcnow()
        need.updated_at = datetime.utcnow()

        candidate = None
        if need.candidate_id is not None:
            candidate = (
                self.db.query(CandidateIntervention)
                .filter(CandidateIntervention.id == need.candidate_id)
                .one_or_none()
            )
        if candidate is not None:
            self._apply_resolution(user, candidate, need, payload, allow_state_update)

        self.db.flush()
        WorldModelService(self.db).append_event(
            user,
            EventCreate(
                event_type="information.need_resolved",
                source=payload.source,
                subject_type="information_need",
                subject_id=str(need.id),
                payload={
                    "candidate_id": need.candidate_id,
                    "need_type": need.need_type,
                    "resolution_confidence": need.resolution_confidence,
                    "provenance": need.resolution_provenance,
                },
                confidence=need.resolution_confidence,
                correlation_id=(
                    f"candidate:{need.candidate_id}" if need.candidate_id is not None else ""
                ),
            ),
            commit=False,
        )
        self.db.commit()
        if candidate is not None:
            self._maybe_requeue(candidate, need.future_run_id)
        self.db.refresh(need)
        return need

    def waive(self, user: User, need: InformationNeed, reason: str) -> InformationNeed:
        if need.user_id != user.id:
            raise ValueError("information need does not belong to user")
        if need.status == "resolved":
            raise ValueError("resolved need cannot be waived")
        need.status = "waived"
        need.resolution = {"waive_reason": reason}
        need.resolution_source = "user"
        need.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(need)
        return need

    def claim_user_questions(self, user: User, requested: int = 5) -> list[InformationNeed]:
        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        policy = mandate.notification_policy if mandate else {}
        daily_budget = int(policy.get("max_questions_per_day", 2))
        daily_budget = max(0, min(daily_budget, 10))
        already_asked = (
            self.db.query(InformationNeed)
            .filter(
                InformationNeed.user_id == user.id,
                InformationNeed.last_asked_at.is_not(None),
            )
            .all()
        )
        today = date.today()
        asked_today = sum(
            1
            for item in already_asked
            if item.last_asked_at is not None and item.last_asked_at.date() == today
        )
        remaining = max(0, daily_budget - asked_today)
        limit = min(max(0, requested), remaining)
        if limit == 0:
            return []

        open_needs = (
            self.db.query(InformationNeed)
            .filter(
                InformationNeed.user_id == user.id,
                InformationNeed.status == "open",
            )
            .all()
        )
        open_needs.sort(
            key=lambda item: (
                PRIORITY_ORDER.get(item.priority, 9),
                item.ask_count,
                item.created_at,
            )
        )
        selected = open_needs[:limit]
        now = datetime.utcnow()
        for need in selected:
            need.ask_count += 1
            need.last_asked_at = now
            need.updated_at = now
        self.db.commit()
        if selected:
            WorldModelService(self.db).append_event(
                user,
                EventCreate(
                    event_type="information.questions_claimed",
                    source="attention_policy",
                    subject_type="information_batch",
                    subject_id=now.isoformat(),
                    payload={
                        "need_ids": [item.id for item in selected],
                        "daily_budget": daily_budget,
                        "asked_today_before_batch": asked_today,
                    },
                ),
            )
        return selected

    def _apply_resolution(
        self,
        user: User,
        candidate: CandidateIntervention,
        need: InformationNeed,
        payload: InformationResolution,
        allow_state_update: bool,
    ) -> None:
        if need.need_type == "verify_assumption":
            assumptions = [dict(item) for item in (candidate.assumptions or [])]
            question = need.question.strip()
            for assumption in assumptions:
                statement = str(assumption.get("statement", "")).strip()
                falsifier = str(assumption.get("falsifiable_by", "")).strip()
                if question in {statement, falsifier}:
                    assumption["confidence"] = max(
                        float(assumption.get("confidence", 0.0)), payload.confidence
                    )
                    assumption["verified_by"] = {
                        "source": payload.source,
                        "provenance": payload.provenance,
                    }
            candidate.assumptions = assumptions

        elif need.need_type == "check_reversibility":
            intervention = dict(candidate.intervention or {})
            for key in ("reversible", "lock_in_days", "reversal_cost"):
                if key in payload.value:
                    intervention[key] = payload.value[key]
            candidate.intervention = intervention

        elif need.need_type in {"reduce_sign_uncertainty", "model_effects"}:
            effects = payload.value.get("effects")
            if isinstance(effects, dict) and effects:
                candidate.effects = effects

        elif need.need_type == "resolve_missing_state" and allow_state_update:
            unknown = need.question.split(":", 1)[-1].strip()
            raw_value = payload.value.get("value")
            if (
                unknown in FINANCIAL_UNKNOWN_FIELDS
                and isinstance(raw_value, (int, float))
                and payload.source in {"user", "verified_connector", "connected_read_only_source"}
                and payload.confidence >= 0.8
            ):
                setattr(user, unknown, float(raw_value))

            state_fact = payload.value.get("state_fact")
            if isinstance(state_fact, dict):
                domain = str(state_fact.get("domain", "")).strip()
                key = str(state_fact.get("key", "")).strip()
                value = state_fact.get("value")
                if domain and key and isinstance(value, dict):
                    self.db.query(StateFact).filter(
                        StateFact.user_id == user.id,
                        StateFact.domain == domain,
                        StateFact.key == key,
                        StateFact.superseded == False,  # noqa: E712
                    ).update({StateFact.superseded: True}, synchronize_session=False)
                    self.db.add(
                        StateFact(
                            user_id=user.id,
                            domain=domain,
                            key=key,
                            value=value,
                            source=payload.source,
                            provenance=payload.provenance,
                            confidence=payload.confidence,
                            sensitivity=need.sensitivity,
                        )
                    )

        evidence = dict(candidate.evidence or {})
        sources = list(evidence.get("sources", []))
        marker = f"information_need:{need.id}"
        if marker not in sources:
            sources.append(marker)
        evidence["sources"] = sources
        evidence["resolution_notes"] = "candidate model updated from explicit information resolution"
        candidate.evidence = evidence
        candidate.updated_at = datetime.utcnow()

    def _maybe_requeue(self, candidate: CandidateIntervention, future_run_id: int | None) -> None:
        query = self.db.query(InformationNeed).filter(
            InformationNeed.candidate_id == candidate.id,
            InformationNeed.blocks_candidate == True,  # noqa: E712
        )
        if future_run_id is not None:
            query = query.filter(InformationNeed.future_run_id == future_run_id)
        needs = query.all()
        if not needs:
            return
        if any(item.status != "resolved" for item in needs):
            return
        if any(float(item.resolution_confidence) < 0.5 for item in needs):
            return
        candidate.status = "generated"
        candidate.rejection_reason = ""
        candidate.future_run_id = None
        candidate.scenario_id = None
        candidate.decision_status = ""
        candidate.updated_at = datetime.utcnow()
        self.db.commit()

    def _open_count(self, user: User) -> int:
        return (
            self.db.query(InformationNeed)
            .filter(
                InformationNeed.user_id == user.id,
                InformationNeed.status == "open",
            )
            .count()
        )
