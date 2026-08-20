from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..services.horizon_world_coverage import HorizonWorldCoverageService


router = APIRouter(prefix="/horizon/world", dependencies=[Depends(require_api_key)])


@router.get("/coverage")
def world_coverage(db: Session = Depends(get_db)):
    return HorizonWorldCoverageService(db).snapshot()
