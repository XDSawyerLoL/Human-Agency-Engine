from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_corpus_schemas import HorizonCalibrationCorpusBuildRequest
from ..models import User
from ..security import require_api_key
from ..services.horizon_corpus import HorizonCalibrationCorpusService

router = APIRouter(prefix="/horizon/corpus", dependencies=[Depends(require_api_key)])


def _user_or_404(db: Session, external_id: str) -> User:
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if user is None:
        raise HTTPException(404, "HORIZON user not found")
    return user


@router.post("/users/{external_id}/build")
def build_calibration_corpus(
    external_id: str,
    payload: HorizonCalibrationCorpusBuildRequest,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return HorizonCalibrationCorpusService(db).build(user, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/users/{external_id}/runs")
def list_calibration_corpus_runs(
    external_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    return HorizonCalibrationCorpusService(db).list_runs(user, limit=limit)


@router.get("/users/{external_id}/runs/{run_id}")
def get_calibration_corpus_run(
    external_id: str,
    run_id: int,
    db: Session = Depends(get_db),
):
    user = _user_or_404(db, external_id)
    try:
        return HorizonCalibrationCorpusService(db).get_run(user, run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402
agency_router.include_router(router)
