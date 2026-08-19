from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..services.horizon_normalizer import HorizonMeteoFranceNormalizer

router = APIRouter(prefix="/horizon/normalize", dependencies=[Depends(require_api_key)])


@router.post("/meteofrance/latest")
def normalize_latest_meteofrance(db: Session = Depends(get_db)):
    try:
        return HorizonMeteoFranceNormalizer(db).normalize_latest()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/meteofrance/{observation_id}")
def normalize_meteofrance_observation(observation_id: int, db: Session = Depends(get_db)):
    try:
        return HorizonMeteoFranceNormalizer(db).normalize(observation_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
