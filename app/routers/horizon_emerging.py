from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_emerging_schemas import HorizonEmergingClusterRequest
from ..security import require_api_key
from ..services.horizon_emerging import HorizonEmergingService

router = APIRouter(prefix="/horizon", dependencies=[Depends(require_api_key)])


@router.post("/emerging/gdelt/cluster")
def cluster_gdelt_candidates(
    payload: HorizonEmergingClusterRequest,
    db: Session = Depends(get_db),
):
    return HorizonEmergingService(db).cluster_gdelt(payload)


from .agency import router as agency_router
agency_router.include_router(router)
