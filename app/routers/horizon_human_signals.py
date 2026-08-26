from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from ..services.evidence_forecast_engine import EvidenceForecastEngine
from ..services.horizon_briefing import HorizonWorldBriefingService
from ..services.horizon_event_graph import HorizonEventGraphService
from ..services.human_signal_engine import HumanSignalEngine
from ..services.solution_scan import SolutionScanService


router = APIRouter()


@router.get("/human-signals/forecasts")
def human_signal_forecasts(
    limit: int = Query(default=12, ge=1, le=100),
    event_limit: int = Query(default=200, ge=1, le=500),
    candidate_limit: int = Query(default=200, ge=1, le=500),
    lookback_hours: int = Query(default=336, ge=24, le=24 * 90),
    db: Session = Depends(get_db),
):
    """Project falsifiable public-world scenarios from converging HORIZON evidence."""
    briefing = HorizonWorldBriefingService(db).snapshot(
        external_id=None,
        event_limit=event_limit,
        candidate_limit=candidate_limit,
        forecast_limit=1,
    )
    graph_result = HorizonEventGraphService(db).build(
        HorizonEventGraphBuildRequest(
            lookback_hours=lookback_hours,
            max_events=event_limit,
            max_candidates=candidate_limit,
            max_signals=min(2000, max(400, (event_limit + candidate_limit) * 3)),
        )
    )
    return EvidenceForecastEngine().forecast(
        briefing,
        graph=graph_result.get("graph_snapshot") or {},
        limit=limit,
    )


@router.get("/human-signals/opportunities")
def human_signal_opportunities(
    external_id: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=20, ge=1, le=100),
    event_limit: int = Query(default=120, ge=1, le=200),
    candidate_limit: int = Query(default=120, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Legacy diagnostic surface kept for compatibility; Évidence public uses /forecasts."""
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
