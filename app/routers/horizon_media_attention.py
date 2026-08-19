from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_behavioral_signal_schemas import HorizonMediaAttentionRefreshRequest
from ..security import require_api_key
from ..services.horizon_media_attention import HorizonMediaAttentionService

router = APIRouter(prefix="/horizon/signals", dependencies=[Depends(require_api_key)])


@router.post("/media-attention/refresh")
def refresh_media_attention(
    payload: HorizonMediaAttentionRefreshRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonMediaAttentionService(db).refresh(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
