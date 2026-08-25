from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.horizon_briefing import HorizonWorldBriefingService
from ..services.human_signal_engine import HumanSignalEngine
from ..services.solution_scan import SolutionScanService


router = APIRouter()


@router.get("/human-signals/opportunities")
def human_signal_opportunities(
    external_id: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=20, ge=1, le=100),
    event_limit: int = Query(default=120, ge=1, le=200),
    candidate_limit: int = Query(default=120, ge=1, le=200),
    db: Session = Depends(get_db),
):
    briefing = HorizonWorldBriefingService(db).snapshot(
        external_id=external_id,
        event_limit=event_limit,
        candidate_limit=candidate_limit,
        forecast_limit=1,
    )
    return HumanSignalEngine().analyze(briefing, limit=limit)


@router.get("/human-signals/solution-scan")
def human_signal_solution_scan(
    problem_key: str = Query(..., min_length=3, max_length=220),
    external_id: str | None = Query(default=None, max_length=160),
    max_results_per_source: int = Query(default=10, ge=3, le=20),
    db: Session = Depends(get_db),
):
    briefing = HorizonWorldBriefingService(db).snapshot(
        external_id=external_id,
        event_limit=200,
        candidate_limit=200,
        forecast_limit=1,
    )
    opportunities = HumanSignalEngine().analyze(briefing, limit=100)["opportunities"]
    opportunity = next(
        (item for item in opportunities if item.get("problem_key") == problem_key),
        None,
    )
    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Problem signal not found in the current HORIZON briefing",
        )
    return SolutionScanService().scan(
        opportunity,
        max_results_per_source=max_results_per_source,
    )
