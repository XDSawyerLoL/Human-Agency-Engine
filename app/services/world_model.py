from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import FutureScenario, User
from ..world_models import (
    Experiment,
    ExperimentObservation,
    HypothesisEvidence,
    WorldEvent,
    WorldHypothesis,
)
from ..world_schemas import (
    EventCreate,
    EvidenceCreate,
    ExperimentCreate,
    ExperimentObservationCreate,
    HypothesisCreate,
)


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _event_digest(*, previous_hash: str, event_type: str, source: str, subject_type: str, subject_id: str, payload: dict, confidence: float, occurred_at: datetime, causation_id: str, correlation_id: str) -> str:
    material = {
        "previous_hash": previous_hash,
        "event_type": event_type,
        "source": source,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "payload": payload,
        "confidence": round(float(confidence), 6),
        "occurred_at": occurred_at.isoformat(),
        "causation_id": causation_id,
        "correlation_id": correlation_id,
    }
    return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()


class WorldModelService:
    def __init__(self, db: Session):
        self.db = db

    def append_event(self, user: User, payload: EventCreate, *, commit: bool = True) -> WorldEvent:
        previous = (
            self.db.query(WorldEvent)
            .filter(WorldEvent.user_id == user.id)
            .order_by(WorldEvent.id.desc())
            .first()
        )
        previous_hash = previous.event_hash if previous else ""
        occurred_at = payload.occurred_at or datetime.utcnow()
        event_hash = _event_digest(
            previous_hash=previous_hash,
            event_type=payload.event_type,
            source=payload.source,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            payload=payload.payload,
            confidence=payload.confidence,
            occurred_at=occurred_at,
            causation_id=payload.causation_id,
            correlation_id=payload.correlation_id,
        )
        event = WorldEvent(
            user_id=user.id,
            event_type=payload.event_type,
            source=payload.source,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            payload=payload.payload,
            confidence=payload.confidence,
            occurred_at=occurred_at,
            causation_id=payload.causation_id,
            correlation_id=payload.correlation_id,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self.db.add(event)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    def verify_chain(self, user: User) -> dict:
        events = (
            self.db.query(WorldEvent)
            .filter(WorldEvent.user_id == user.id)
            .order_by(WorldEvent.id.asc())
            .all()
        )
        previous_hash = ""
        for index, event in enumerate(events):
            expected = _event_digest(
                previous_hash=previous_hash,
                event_type=event.event_type,
                source=event.source,
                subject_type=event.subject_type,
                subject_id=event.subject_id,
                payload=event.payload,
                confidence=event.confidence,
                occurred_at=event.occurred_at,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
            )
            if event.previous_hash != previous_hash or event.event_hash != expected:
                return {
                    "valid": False,
                    "event_count": len(events),
                    "first_invalid_event_id": event.id,
                    "position": index,
                }
            previous_hash = event.event_hash
        return {
            "valid": True,
            "event_count": len(events),
            "head_hash": previous_hash,
        }

    def create_hypothesis(self, user: User, payload: HypothesisCreate) -> WorldHypothesis:
        hypothesis = WorldHypothesis(user_id=user.id, **payload.model_dump())
        self.db.add(hypothesis)
        self.db.flush()
        self.append_event(
            user,
            EventCreate(
                event_type="hypothesis.created",
                source="world_model",
                subject_type="hypothesis",
                subject_id=str(hypothesis.id),
                payload={
                    "name": hypothesis.name,
                    "cause_pattern": hypothesis.cause_pattern,
                    "effect_pattern": hypothesis.effect_pattern,
                    "claim_level": hypothesis.claim_level,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(hypothesis)
        return hypothesis

    def create_experiment(self, user: User, payload: ExperimentCreate) -> Experiment:
        if payload.scenario_id is not None:
            scenario = self.db.query(FutureScenario).filter(FutureScenario.id == payload.scenario_id).one_or_none()
            if not scenario:
                raise ValueError("future scenario not found")
        if payload.hypothesis_id is not None:
            hypothesis = (
                self.db.query(WorldHypothesis)
                .filter(WorldHypothesis.id == payload.hypothesis_id, WorldHypothesis.user_id == user.id)
                .one_or_none()
            )
            if not hypothesis:
                raise ValueError("hypothesis not found for user")

        experiment = Experiment(user_id=user.id, **payload.model_dump())
        self.db.add(experiment)
        self.db.flush()
        self.append_event(
            user,
            EventCreate(
                event_type="experiment.proposed",
                source="decision_lab",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={
                    "title": experiment.title,
                    "reversible": experiment.reversible,
                    "intervention": experiment.intervention,
                    "stop_conditions": experiment.stop_conditions,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def authorize_experiment(self, user: User, experiment: Experiment, *, confirm: str, irreversible_ack: bool = False) -> Experiment:
        required = f"AUTHORIZE {experiment.id}"
        if confirm != required:
            raise ValueError(f"confirmation must equal: {required}")
        if not experiment.reversible and not irreversible_ack:
            raise ValueError("irreversible experiment requires explicit irreversible_ack")
        if experiment.authorization_status not in {"proposed", "rejected"}:
            raise ValueError("experiment authorization state does not allow authorization")

        experiment.authorization_status = "authorized"
        experiment.authorized_at = datetime.utcnow()
        self.append_event(
            user,
            EventCreate(
                event_type="experiment.authorized",
                source="user",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={"reversible": experiment.reversible, "irreversible_ack": irreversible_ack},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def start_experiment(self, user: User, experiment: Experiment) -> Experiment:
        if experiment.authorization_status != "authorized":
            raise ValueError("experiment must be authorized before start")
        if experiment.execution_status not in {"planned", "stopped", "rolled_back"}:
            raise ValueError("experiment cannot be started from current state")
        experiment.execution_status = "running"
        experiment.started_at = datetime.utcnow()
        self.append_event(
            user,
            EventCreate(
                event_type="experiment.started",
                source="system",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={"intervention": experiment.intervention},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def record_observation(self, user: User, experiment: Experiment, payload: ExperimentObservationCreate) -> ExperimentObservation:
        observation = ExperimentObservation(experiment_id=experiment.id, **payload.model_dump())
        self.db.add(observation)
        self.db.flush()

        event = self.append_event(
            user,
            EventCreate(
                event_type="experiment.observed",
                source="observation",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={
                    "metrics": observation.metrics,
                    "verdict": observation.verdict,
                    "quality": observation.quality,
                    "notes": observation.notes,
                },
                confidence=observation.quality,
            ),
            commit=False,
        )

        if experiment.hypothesis_id is not None:
            evidence = EvidenceCreate(
                event_id=event.id,
                experiment_id=experiment.id,
                observation_id=observation.id,
                verdict=observation.verdict,
                quality=observation.quality,
                notes=observation.notes,
            )
            self._add_evidence(experiment.hypothesis_id, evidence)

        self.db.commit()
        self.db.refresh(observation)
        return observation

    def complete_experiment(self, user: User, experiment: Experiment) -> Experiment:
        if experiment.execution_status != "running":
            raise ValueError("only running experiments can be completed")
        experiment.execution_status = "completed"
        experiment.completed_at = datetime.utcnow()
        self.append_event(
            user,
            EventCreate(
                event_type="experiment.completed",
                source="system",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def rollback_experiment(self, user: User, experiment: Experiment) -> Experiment:
        if not experiment.reversible:
            raise ValueError("experiment is not marked reversible")
        if not experiment.rollback_plan:
            raise ValueError("reversible experiment has no rollback plan")
        if experiment.execution_status not in {"running", "completed", "stopped"}:
            raise ValueError("experiment cannot be rolled back from current state")
        experiment.execution_status = "rolled_back"
        experiment.completed_at = datetime.utcnow()
        self.append_event(
            user,
            EventCreate(
                event_type="experiment.rolled_back",
                source="user",
                subject_type="experiment",
                subject_id=str(experiment.id),
                payload={"rollback_plan": experiment.rollback_plan},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def add_evidence(self, user: User, hypothesis: WorldHypothesis, payload: EvidenceCreate) -> HypothesisEvidence:
        if hypothesis.user_id != user.id:
            raise ValueError("hypothesis does not belong to user")
        evidence = self._add_evidence(hypothesis.id, payload)
        self.append_event(
            user,
            EventCreate(
                event_type="hypothesis.evidence_added",
                source="world_model",
                subject_type="hypothesis",
                subject_id=str(hypothesis.id),
                payload={
                    "verdict": payload.verdict,
                    "quality": payload.quality,
                    "evidence_id": evidence.id,
                },
                confidence=payload.quality,
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def _add_evidence(self, hypothesis_id: int, payload: EvidenceCreate) -> HypothesisEvidence:
        hypothesis = self.db.query(WorldHypothesis).filter(WorldHypothesis.id == hypothesis_id).one_or_none()
        if not hypothesis:
            raise ValueError("hypothesis not found")

        evidence = HypothesisEvidence(hypothesis_id=hypothesis.id, **payload.model_dump())
        self.db.add(evidence)
        self.db.flush()

        all_evidence = (
            self.db.query(HypothesisEvidence)
            .filter(HypothesisEvidence.hypothesis_id == hypothesis.id)
            .all()
        )
        supports = [item for item in all_evidence if item.verdict == "supports"]
        contradictions = [item for item in all_evidence if item.verdict == "contradicts"]
        inconclusive = [item for item in all_evidence if item.verdict == "inconclusive"]
        decisive = supports + contradictions

        hypothesis.support_count = len(supports)
        hypothesis.contradiction_count = len(contradictions)
        hypothesis.inconclusive_count = len(inconclusive)
        hypothesis.updated_at = datetime.utcnow()

        if decisive:
            total_quality = sum(float(item.quality) for item in decisive)
            weighted_support = sum(float(item.quality) for item in supports)
            consistency = weighted_support / total_quality if total_quality else 0.0
            evidence_mass = min(1.0, total_quality / 4.0)
            hypothesis.confidence = round(min(0.95, consistency * evidence_mass), 4)
        else:
            hypothesis.confidence = 0.0

        experiment_supports = [
            item for item in supports if item.experiment_id is not None and float(item.quality) >= 0.6
        ]
        experiment_contradictions = [
            item for item in contradictions if item.experiment_id is not None and float(item.quality) >= 0.6
        ]
        if len(experiment_supports) >= 3 and len(experiment_contradictions) <= 1 and hypothesis.confidence >= 0.55:
            hypothesis.claim_level = "personal_empirical"
        else:
            hypothesis.claim_level = "correlation"

        # causal_supported is intentionally never assigned automatically.
        return evidence
