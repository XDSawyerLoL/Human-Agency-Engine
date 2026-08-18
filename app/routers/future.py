from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..future_schemas import ForecastOutcomeCreate, FutureCompareRequest
from ..models import ForecastOutcome, FutureRun, FutureScenario, User
from ..security import require_api_key
from ..services.decision_lab import DecisionLab
from ..services.future import FutureEngine
from ..services.world_model import WorldModelService
from ..world_schemas import EventCreate

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _scenario_dict(item: FutureScenario) -> dict:
    return {
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
        "created_at": item.created_at,
    }


@router.post("/users/{external_id}/future/compare")
def compare_futures(
    external_id: str,
    payload: FutureCompareRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    run, scenarios = FutureEngine(db).compare(user, payload)
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="future.run_created",
            source="future_engine",
            subject_type="future_run",
            subject_id=str(run.id),
            payload={
                "horizon_days": run.horizon_days,
                "objective": run.objective,
                "scenario_ids": [item.id for item in scenarios],
                "scenario_count": len(scenarios),
            },
            correlation_id=f"future-run:{run.id}",
        ),
    )
    return {
        "run": {
            "id": run.id,
            "horizon_days": run.horizon_days,
            "objective": run.objective,
            "engine_version": run.engine_version,
            "created_at": run.created_at,
            "state_snapshot": run.state_snapshot,
            "intent_snapshot": run.intent_snapshot,
            "mandate_snapshot": run.mandate_snapshot,
        },
        "scenarios": [_scenario_dict(item) for item in scenarios],
        "interpretation": {
            "confidence_is_probability": False,
            "bounds_are_probability_intervals": False,
            "default_claim": "projection, unless evidence level supports a stronger claim",
        },
    }


@router.get("/users/{external_id}/future/runs")
def list_future_runs(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    runs = (
        db.query(FutureRun)
        .filter(FutureRun.user_id == user.id)
        .order_by(FutureRun.created_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "horizon_days": item.horizon_days,
            "objective": item.objective,
            "engine_version": item.engine_version,
            "created_at": item.created_at,
        }
        for item in runs
    ]


@router.get("/future/runs/{run_id}")
def get_future_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(FutureRun).filter(FutureRun.id == run_id).one_or_none()
    if not run:
        raise HTTPException(404, "future run not found")
    scenarios = (
        db.query(FutureScenario)
        .filter(FutureScenario.run_id == run.id)
        .order_by(FutureScenario.id.asc())
        .all()
    )
    return {
        "run": {
            "id": run.id,
            "user_id": run.user_id,
            "horizon_days": run.horizon_days,
            "objective": run.objective,
            "state_snapshot": run.state_snapshot,
            "intent_snapshot": run.intent_snapshot,
            "mandate_snapshot": run.mandate_snapshot,
            "engine_version": run.engine_version,
            "created_at": run.created_at,
        },
        "scenarios": [_scenario_dict(item) for item in scenarios],
    }


@router.get("/future/runs/{run_id}/decision-lab")
def decision_lab(run_id: int, db: Session = Depends(get_db)):
    run = db.query(FutureRun).filter(FutureRun.id == run_id).one_or_none()
    if not run:
        raise HTTPException(404, "future run not found")
    return DecisionLab(db).analyze(run)


@router.post("/future/runs/{run_id}/outcomes")
def record_forecast_outcome(
    run_id: int,
    payload: ForecastOutcomeCreate,
    db: Session = Depends(get_db),
):
    run = db.query(FutureRun).filter(FutureRun.id == run_id).one_or_none()
    if not run:
        raise HTTPException(404, "future run not found")

    if payload.scenario_id is not None:
        scenario = (
            db.query(FutureScenario)
            .filter(
                FutureScenario.id == payload.scenario_id,
                FutureScenario.run_id == run.id,
            )
            .one_or_none()
        )
        if not scenario:
            raise HTTPException(400, "scenario does not belong to future run")

    outcome = ForecastOutcome(
        run_id=run.id,
        scenario_id=payload.scenario_id,
        observed_metrics=payload.observed_metrics,
        observation_window=payload.observation_window,
        notes=payload.notes,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    user = db.query(User).filter(User.id == run.user_id).one()
    WorldModelService(db).append_event(
        user,
        EventCreate(
            event_type="future.outcome_observed",
            source="observation",
            subject_type="forecast_outcome",
            subject_id=str(outcome.id),
            payload={
                "run_id": run.id,
                "scenario_id": outcome.scenario_id,
                "observed_metric_names": sorted(outcome.observed_metrics.keys()),
                "observation_window": outcome.observation_window,
            },
            correlation_id=f"future-run:{run.id}",
        ),
    )
    return {
        "id": outcome.id,
        "run_id": outcome.run_id,
        "scenario_id": outcome.scenario_id,
        "recorded_at": outcome.recorded_at,
    }


@router.get("/users/{external_id}/future/calibration")
def future_calibration(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return FutureEngine(db).calibration(user)
