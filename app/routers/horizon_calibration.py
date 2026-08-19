from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.horizon_calibration import HorizonEmpiricalCalibrationService

router = APIRouter(prefix="/horizon/calibration", dependencies=[Depends(require_api_key)])


@router.get("/users/{external_id}/profile")
def calibration_profile(
    external_id: str,
    mode: str = Query(default="backtest", pattern="^(backtest|live|all)$"),
    as_of: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if not user:
        raise HTTPException(404, "user not found")
    return HorizonEmpiricalCalibrationService(db).profile(user, mode=mode, as_of=as_of)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
