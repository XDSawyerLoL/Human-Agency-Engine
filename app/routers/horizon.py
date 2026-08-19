from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_models import HorizonForecast, HorizonGlobalEvent
from ..horizon_schemas import (
    HorizonEventCreate,
    HorizonForecastRequest,
    HorizonPatternCreate,
    HorizonResolutionCreate,
    HorizonSignalCreate,
)
from ..models import User
from ..security import require_api_key
from ..services.horizon import HorizonService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _forecast_out(row: HorizonForecast) -> dict:
    return {
        "id": row.id,
        "forecast_key": row.forecast_key,
        "event_id": row.event_id,
        "pattern_id": row.pattern_id,
        "mode": row.mode,
        "as_of": row.as_of,
        "fact_layer": row.event_facts_snapshot,
        "social_signal_layer": row.social_signal_snapshot,
        "personal_exposure_layer": row.personal_exposure,
        "forecast_layer": {
            "predicted_outcome": row.predicted_outcome,
            "behavior_chain": row.behavior_chain,
            "likelihood_band": row.likelihood_band,
            "predictive_score": row.predictive_score,
            "predictive_score_is_probability": False,
            "probability_interval": {
                "low": row.probability_low,
                "mid": row.probability_mid,
                "high": row.probability_high,
                "basis": row.probability_basis,
            },
            "expected_onset_low": row.expected_onset_low,
            "expected_onset_high": row.expected_onset_high,
            "decision_window": row.decision_window,
            "reasons": row.reasons,
        },
        "calibration_status": row.calibration_status,
        "status": row.status,
        "created_at": row.created_at,
    }


@router.post("/events")
def create_event(payload: HorizonEventCreate, db: Session = Depends(get_db)):
    try:
        row = HorizonService(db).create_event(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "id": row.id,
        "event_key": row.event_key,
        "event_type": row.event_type,
        "title": row.title,
        "fact_layer": row.raw_facts,
        "source": row.source,
        "source_reliability": row.source_reliability,
        "occurred_at": row.occurred_at,
        "first_observed_at": row.first_observed_at,
        "immutable_snapshot": True,
    }


@router.get("/events")
def list_events(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(HorizonGlobalEvent)
    if active_only:
        query = query.filter(HorizonGlobalEvent.status == "active")
    rows = query.order_by(HorizonGlobalEvent.first_observed_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "event_key": row.event_key,
            "event_type": row.event_type,
            "title": row.title,
            "summary": row.summary,
            "geography": row.geography,
            "source": row.source,
            "source_url": row.source_url,
            "source_reliability": row.source_reliability,
            "occurred_at": row.occurred_at,
            "first_observed_at": row.first_observed_at,
        }
        for row in rows
    ]


@router.post("/events/{event_id}/signals")
def add_social_signal(event_id: int, payload: HorizonSignalCreate, db: Session = Depends(get_db)):
    try:
        row = HorizonService(db).add_signal(event_id, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "id": row.id,
        "event_id": row.event_id,
        "signal_key": row.signal_key,
        "signal_type": row.signal_type,
        "normalized_score": row.normalized_score,
        "normalized_score_is_probability": False,
        "direction": row.direction,
        "reliability": row.reliability,
        "observed_at": row.observed_at,
    }


@router.post("/patterns")
def create_behavior_pattern(payload: HorizonPatternCreate, db: Session = Depends(get_db)):
    try:
        row = HorizonService(db).create_pattern(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "id": row.id,
        "pattern_key": row.pattern_key,
        "name": row.name,
        "predicted_response": row.predicted_response,
        "mechanism_chain": row.mechanism_chain,
        "knowledge_available_at": row.knowledge_available_at,
        "confidence": row.confidence,
    }


@router.post("/users/{external_id}/forecast")
def forecast_for_user(
    external_id: str,
    payload: HorizonForecastRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        rows = HorizonService(db).forecast_user(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "engine": HorizonService.ENGINE_VERSION,
        "mode": payload.mode,
        "forecasts": [_forecast_out(row) for row in rows],
        "numeric_probabilities_enabled": False,
        "backtest_no_future_leakage_guards": payload.mode == "backtest",
    }


@router.get("/users/{external_id}/forecasts")
def list_user_forecasts(
    external_id: str,
    mode: str | None = Query(default=None, pattern="^(live|backtest)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    query = db.query(HorizonForecast).filter(HorizonForecast.user_id == user.id)
    if mode:
        query = query.filter(HorizonForecast.mode == mode)
    rows = query.order_by(HorizonForecast.as_of.desc(), HorizonForecast.id.desc()).limit(limit).all()
    return [_forecast_out(row) for row in rows]


@router.put("/forecasts/{forecast_id}/resolution")
def resolve_forecast(
    forecast_id: int,
    payload: HorizonResolutionCreate,
    db: Session = Depends(get_db),
):
    forecast = db.query(HorizonForecast).filter(HorizonForecast.id == forecast_id).one_or_none()
    if not forecast:
        raise HTTPException(404, "HORIZON forecast not found")
    try:
        row = HorizonService(db).resolve_forecast(forecast, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "forecast_id": forecast.id,
        "correctness": row.correctness,
        "outcome_occurred": row.outcome_occurred,
        "predictive_lead_time_hours": row.predictive_lead_time_hours,
        "actionable_lead_time_hours": row.actionable_lead_time_hours,
        "became_obvious_at": row.became_obvious_at,
        "resolved_at": row.resolved_at,
    }


@router.get("/users/{external_id}/calibration")
def calibration_summary(external_id: str, db: Session = Depends(get_db)):
    user = _user_or_404(db, external_id)
    return HorizonService(db).calibration_summary(user)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
