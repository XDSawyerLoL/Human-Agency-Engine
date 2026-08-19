from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..security import require_api_key
from ..services.horizon_meteofrance import HorizonMeteoFranceService

router = APIRouter(prefix="/horizon/live", dependencies=[Depends(require_api_key)])


@router.post("/meteofrance/poll")
def poll_meteofrance(db: Session = Depends(get_db)):
    if not settings.meteofrance_application_id:
        return {
            "source_key": "meteofrance-vigilance",
            "configured": False,
            "skipped": True,
            "reason": "METEOFRANCE_APPLICATION_ID is not configured",
            "new_observations": 0,
            "candidates_created": 0,
            "promoted_events": 0,
        }
    try:
        return HorizonMeteoFranceService(db).poll(settings.meteofrance_application_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
