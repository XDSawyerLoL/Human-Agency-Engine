from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_backtest_schemas import HorizonHistoricalBacktestRequest
from ..models import User
from ..security import require_api_key
from ..services.horizon_backtest_coverage import HorizonCoverageAwareHistoricalBacktestFactory

router = APIRouter(prefix="/horizon/backtests", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return user


@router.post("/users/{external_id}/run")
def run_historical_backtest(
    external_id: str,
    payload: HorizonHistoricalBacktestRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return HorizonCoverageAwareHistoricalBacktestFactory(db).run(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/users/{external_id}/runs")
def list_historical_backtest_runs(
    external_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    return HorizonCoverageAwareHistoricalBacktestFactory(db).list_runs(user, limit=limit)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
