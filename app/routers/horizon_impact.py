from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_impact_models import HorizonPersonalImpactAssessment
from ..horizon_impact_schemas import HorizonImpactRequest
from ..models import User
from ..security import require_api_key
from ..services.horizon_impact import HorizonImpactService

router = APIRouter(prefix="/horizon/impact", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


def _out(row: HorizonPersonalImpactAssessment) -> dict:
    return {
        "id": row.id,
        "assessment_key": row.assessment_key,
        "event_id": row.event_id,
        "pattern_id": row.pattern_id,
        "forecast_id": row.forecast_id,
        "cascade_id": row.cascade_id,
        "mode": row.mode,
        "as_of": row.as_of,
        "fact_layer": row.fact_layer,
        "collective_behavior_layer": row.collective_behavior_layer,
        "personal_exposure_layer": row.personal_exposure_layer,
        "timing_layer": row.timing_layer,
        "impact_score": row.impact_score,
        "urgency_score": row.urgency_score,
        "attention_score": row.attention_score,
        "attention_score_is_probability": False,
        "attention_band": row.attention_band,
        "explanation": row.explanation,
        "created_at": row.created_at,
    }


@router.post("/users/{external_id}/assess")
def assess_personal_impact(
    external_id: str,
    payload: HorizonImpactRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        row = HorizonImpactService(db).assess(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "engine": HorizonImpactService.ENGINE_VERSION,
        "assessment": _out(row),
        "raw_information_is_preserved": True,
        "action_prescribed": False,
        "formal_probability_enabled": False,
    }


@router.get("/users/{external_id}")
def list_personal_impacts(
    external_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    rows = db.query(HorizonPersonalImpactAssessment).filter(
        HorizonPersonalImpactAssessment.user_id == user.id
    ).order_by(
        HorizonPersonalImpactAssessment.as_of.desc(),
        HorizonPersonalImpactAssessment.id.desc(),
    ).limit(limit).all()
    return [_out(row) for row in rows]


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
