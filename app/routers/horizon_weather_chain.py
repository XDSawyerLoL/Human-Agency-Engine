from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_weather_chain_schemas import HorizonWeatherChainReconcileRequest
from ..security import require_api_key
from ..services.horizon_weather_chain import HorizonWeatherChainService

router = APIRouter(prefix="/horizon/weather-chains", dependencies=[Depends(require_api_key)])


@router.post("/reconcile")
def reconcile_weather_chains(
    payload: HorizonWeatherChainReconcileRequest,
    db: Session = Depends(get_db),
):
    return HorizonWeatherChainService(db).reconcile(
        max_forecasts=payload.max_forecasts,
        max_chains=payload.max_chains,
    )


@router.get("")
def list_weather_chains(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return HorizonWeatherChainService(db).list_chains(limit=limit)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
