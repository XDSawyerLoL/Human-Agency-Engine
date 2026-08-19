from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_live_schemas import HorizonGdeltPollRequest
from ..security import require_api_key
from ..services.horizon_live import HorizonLiveService

router = APIRouter(prefix="/horizon/live", dependencies=[Depends(require_api_key)])


@router.post("/gdelt/poll")
def poll_gdelt(payload: HorizonGdeltPollRequest, db: Session = Depends(get_db)):
    try:
        result = HorizonLiveService(db).poll_gdelt(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return result


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
