from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ConnectorAccount,
    ForecastOutcome,
    FutureRun,
    FutureScenario,
    IngestionRecord,
    Intent,
    Notification,
    OAuthState,
    Opportunity,
    Outcome,
    PersonalMandate,
    Signal,
    StateFact,
    User,
)
from ..security import require_api_key
from ..world_models import (
    Experiment,
    ExperimentObservation,
    HypothesisEvidence,
    WorldEvent,
    WorldHypothesis,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _dt(value):
    return value.isoformat() if value is not None else None


@router.get("/users/{external_id}/export")
def export_user_data(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    state_facts = db.query(StateFact).filter(StateFact.user_id == user.id).all()
    intents = db.query(Intent).filter(Intent.user_id == user.id).all()
    mandate = db.query(PersonalMandate).filter(PersonalMandate.user_id == user.id).one_or_none()
    signals = db.query(Signal).filter(Signal.user_id == user.id).all()
    opportunities = db.query(Opportunity).filter(Opportunity.user_id == user.id).all()
    opportunity_ids = [item.id for item in opportunities]
    outcomes = db.query(Outcome).filter(Outcome.opportunity_id.in_(opportunity_ids)).all() if opportunity_ids else []
    notifications = db.query(Notification).filter(Notification.user_id == user.id).all()
    connectors = db.query(ConnectorAccount).filter(ConnectorAccount.user_id == user.id).all()

    future_runs = db.query(FutureRun).filter(FutureRun.user_id == user.id).all()
    run_ids = [item.id for item in future_runs]
    future_scenarios = db.query(FutureScenario).filter(FutureScenario.run_id.in_(run_ids)).all() if run_ids else []
    forecast_outcomes = db.query(ForecastOutcome).filter(ForecastOutcome.run_id.in_(run_ids)).all() if run_ids else []

    world_events = db.query(WorldEvent).filter(WorldEvent.user_id == user.id).order_by(WorldEvent.id.asc()).all()
    hypotheses = db.query(WorldHypothesis).filter(WorldHypothesis.user_id == user.id).all()
    hypothesis_ids = [item.id for item in hypotheses]
    experiments = db.query(Experiment).filter(Experiment.user_id == user.id).all()
    experiment_ids = [item.id for item in experiments]
    observations = (
        db.query(ExperimentObservation).filter(ExperimentObservation.experiment_id.in_(experiment_ids)).all()
        if experiment_ids else []
    )
    evidence = (
        db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id.in_(hypothesis_ids)).all()
        if hypothesis_ids else []
    )

    return {
        "user": {
            "external_id": user.external_id,
            "country": user.country,
            "currency": user.currency,
            "timezone": user.timezone,
            "monthly_income": user.monthly_income,
            "monthly_fixed_costs": user.monthly_fixed_costs,
            "liquid_cash": user.liquid_cash,
            "minimum_cash_buffer": user.minimum_cash_buffer,
            "preferences": user.preferences,
            "created_at": _dt(user.created_at),
        },
        "state_facts": [
            {
                "id": item.id,
                "domain": item.domain,
                "key": item.key,
                "value": item.value,
                "source": item.source,
                "provenance": item.provenance,
                "confidence": item.confidence,
                "sensitivity": item.sensitivity,
                "observed_at": _dt(item.observed_at),
                "expires_at": _dt(item.expires_at),
                "superseded": item.superseded,
            }
            for item in state_facts
        ],
        "mandate": None if mandate is None else {
            "mission": mandate.mission,
            "principles": mandate.principles,
            "constraints": mandate.constraints,
            "autonomy": mandate.autonomy,
            "notification_policy": mandate.notification_policy,
            "version": mandate.version,
            "updated_at": _dt(mandate.updated_at),
        },
        "intents": [
            {
                "id": item.id,
                "kind": item.kind,
                "statement": item.statement,
                "target": item.target,
                "priority": item.priority,
                "active": item.active,
                "created_at": _dt(item.created_at),
            }
            for item in intents
        ],
        "signals": [
            {
                "id": item.id,
                "source": item.source,
                "type": item.type,
                "payload": item.payload,
                "observed_at": _dt(item.observed_at),
                "processed": item.processed,
            }
            for item in signals
        ],
        "opportunities": [
            {
                "id": item.id,
                "signal_id": item.signal_id,
                "category": item.category,
                "title": item.title,
                "rationale": item.rationale,
                "proposed_action": item.proposed_action,
                "baseline": item.baseline,
                "counterfactual": item.counterfactual,
                "expected_value": item.expected_value,
                "confidence": item.confidence,
                "care_status": item.care_status,
                "care_reason": item.care_reason,
                "status": item.status,
                "created_at": _dt(item.created_at),
            }
            for item in opportunities
        ],
        "outcomes": [
            {
                "opportunity_id": item.opportunity_id,
                "useful": item.useful,
                "accepted": item.accepted,
                "executed": item.executed,
                "realized_value": item.realized_value,
                "feedback": item.feedback,
                "metadata": item.metadata_json,
                "recorded_at": _dt(item.recorded_at),
            }
            for item in outcomes
        ],
        "notifications": [
            {
                "opportunity_id": item.opportunity_id,
                "channel": item.channel,
                "status": item.status,
                "suppression_reason": item.suppression_reason,
                "priority": item.priority,
                "available_at": _dt(item.available_at),
                "created_at": _dt(item.created_at),
            }
            for item in notifications
        ],
        "future_runs": [
            {
                "id": item.id,
                "horizon_days": item.horizon_days,
                "objective": item.objective,
                "state_snapshot": item.state_snapshot,
                "intent_snapshot": item.intent_snapshot,
                "mandate_snapshot": item.mandate_snapshot,
                "engine_version": item.engine_version,
                "created_at": _dt(item.created_at),
            }
            for item in future_runs
        ],
        "future_scenarios": [
            {
                "id": item.id,
                "run_id": item.run_id,
                "name": item.name,
                "scenario_type": item.scenario_type,
                "intervention": item.intervention,
                "assumptions": item.assumptions,
                "projected_metrics": item.projected_metrics,
                "uncertainty": item.uncertainty,
                "evidence": item.evidence,
                "agency_delta": item.agency_delta,
                "confidence": item.confidence,
                "claim_level": item.claim_level,
                "robustness": item.robustness,
                "created_at": _dt(item.created_at),
            }
            for item in future_scenarios
        ],
        "forecast_outcomes": [
            {
                "id": item.id,
                "run_id": item.run_id,
                "scenario_id": item.scenario_id,
                "observed_metrics": item.observed_metrics,
                "observation_window": item.observation_window,
                "notes": item.notes,
                "recorded_at": _dt(item.recorded_at),
            }
            for item in forecast_outcomes
        ],
        "world_events": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "source": item.source,
                "subject_type": item.subject_type,
                "subject_id": item.subject_id,
                "payload": item.payload,
                "confidence": item.confidence,
                "occurred_at": _dt(item.occurred_at),
                "recorded_at": _dt(item.recorded_at),
                "causation_id": item.causation_id,
                "correlation_id": item.correlation_id,
                "previous_hash": item.previous_hash,
                "event_hash": item.event_hash,
            }
            for item in world_events
        ],
        "world_hypotheses": [
            {
                "id": item.id,
                "name": item.name,
                "cause_pattern": item.cause_pattern,
                "effect_pattern": item.effect_pattern,
                "context": item.context,
                "direction": item.direction,
                "claim_level": item.claim_level,
                "confidence": item.confidence,
                "support_count": item.support_count,
                "contradiction_count": item.contradiction_count,
                "inconclusive_count": item.inconclusive_count,
                "status": item.status,
                "provenance": item.provenance,
                "created_at": _dt(item.created_at),
                "updated_at": _dt(item.updated_at),
            }
            for item in hypotheses
        ],
        "experiments": [
            {
                "id": item.id,
                "scenario_id": item.scenario_id,
                "hypothesis_id": item.hypothesis_id,
                "title": item.title,
                "intervention": item.intervention,
                "expected_effects": item.expected_effects,
                "stop_conditions": item.stop_conditions,
                "rollback_plan": item.rollback_plan,
                "reversible": item.reversible,
                "authorization_status": item.authorization_status,
                "execution_status": item.execution_status,
                "created_at": _dt(item.created_at),
                "authorized_at": _dt(item.authorized_at),
                "started_at": _dt(item.started_at),
                "completed_at": _dt(item.completed_at),
            }
            for item in experiments
        ],
        "experiment_observations": [
            {
                "id": item.id,
                "experiment_id": item.experiment_id,
                "metrics": item.metrics,
                "verdict": item.verdict,
                "quality": item.quality,
                "notes": item.notes,
                "observed_at": _dt(item.observed_at),
            }
            for item in observations
        ],
        "hypothesis_evidence": [
            {
                "id": item.id,
                "hypothesis_id": item.hypothesis_id,
                "event_id": item.event_id,
                "experiment_id": item.experiment_id,
                "observation_id": item.observation_id,
                "verdict": item.verdict,
                "quality": item.quality,
                "notes": item.notes,
                "created_at": _dt(item.created_at),
            }
            for item in evidence
        ],
        "connectors": [
            {
                "provider": item.provider,
                "scopes": item.scopes,
                "enabled": item.enabled,
                "last_synced_at": _dt(item.last_synced_at),
                "last_error": item.last_error,
            }
            for item in connectors
        ],
        "secrets_included": False,
    }


@router.delete("/users/{external_id}")
def delete_user_data(
    external_id: str,
    confirm: str = Query(..., description="Must equal: DELETE <external_id>"),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    if confirm != f"DELETE {external_id}":
        raise HTTPException(400, "explicit deletion confirmation does not match")

    opportunity_ids = [item[0] for item in db.query(Opportunity.id).filter(Opportunity.user_id == user.id).all()]
    connector_ids = [item[0] for item in db.query(ConnectorAccount.id).filter(ConnectorAccount.user_id == user.id).all()]
    run_ids = [item[0] for item in db.query(FutureRun.id).filter(FutureRun.user_id == user.id).all()]
    hypothesis_ids = [item[0] for item in db.query(WorldHypothesis.id).filter(WorldHypothesis.user_id == user.id).all()]
    experiment_ids = [item[0] for item in db.query(Experiment.id).filter(Experiment.user_id == user.id).all()]
    observation_ids = (
        [item[0] for item in db.query(ExperimentObservation.id).filter(ExperimentObservation.experiment_id.in_(experiment_ids)).all()]
        if experiment_ids else []
    )

    if hypothesis_ids:
        db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id.in_(hypothesis_ids)).delete(synchronize_session=False)
    elif observation_ids:
        db.query(HypothesisEvidence).filter(HypothesisEvidence.observation_id.in_(observation_ids)).delete(synchronize_session=False)
    if experiment_ids:
        db.query(ExperimentObservation).filter(ExperimentObservation.experiment_id.in_(experiment_ids)).delete(synchronize_session=False)
        db.query(Experiment).filter(Experiment.id.in_(experiment_ids)).delete(synchronize_session=False)
    db.query(WorldHypothesis).filter(WorldHypothesis.user_id == user.id).delete(synchronize_session=False)
    db.query(WorldEvent).filter(WorldEvent.user_id == user.id).delete(synchronize_session=False)

    if opportunity_ids:
        db.query(Outcome).filter(Outcome.opportunity_id.in_(opportunity_ids)).delete(synchronize_session=False)
    if run_ids:
        db.query(ForecastOutcome).filter(ForecastOutcome.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(FutureScenario).filter(FutureScenario.run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(FutureRun).filter(FutureRun.user_id == user.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user.id).delete(synchronize_session=False)
    db.query(Opportunity).filter(Opportunity.user_id == user.id).delete(synchronize_session=False)
    if connector_ids:
        db.query(IngestionRecord).filter(IngestionRecord.connector_id.in_(connector_ids)).delete(synchronize_session=False)
    db.query(OAuthState).filter(OAuthState.user_id == user.id).delete(synchronize_session=False)
    db.query(ConnectorAccount).filter(ConnectorAccount.user_id == user.id).delete(synchronize_session=False)
    db.query(Signal).filter(Signal.user_id == user.id).delete(synchronize_session=False)
    db.query(StateFact).filter(StateFact.user_id == user.id).delete(synchronize_session=False)
    db.query(Intent).filter(Intent.user_id == user.id).delete(synchronize_session=False)
    db.query(PersonalMandate).filter(PersonalMandate.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()

    return {"deleted": True, "external_id": external_id}
