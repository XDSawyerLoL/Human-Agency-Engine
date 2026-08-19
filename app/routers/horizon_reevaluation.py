from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_reevaluation_schemas import HorizonReevaluationRequest
from ..security import require_api_key
from ..services.horizon_reevaluation import HorizonReevaluationService

router = APIRouter(prefix="/horizon/reevaluate", dependencies=[Depends(require_api_key)])


@router.post("/run")
def run_horizon_reevaluation(
    payload: HorizonReevaluationRequest,
    db: Session = Depends(get_db),
):
    return HorizonReevaluationService(db).run(payload)


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
