from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..horizon_windy_schemas import HorizonWindyPollRequest
from ..security import require_api_key
from ..services.horizon_windy import HorizonWindyService

router = APIRouter(prefix="/horizon/live", dependencies=[Depends(require_api_key)])


@router.post("/windy/poll")
def poll_windy(payload: HorizonWindyPollRequest, db: Session = Depends(get_db)):
    try:
        return HorizonWindyService(db).poll(
            payload,
            settings.windy_point_forecast_api_key,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
