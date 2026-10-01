from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import require_api_key
from ..services.aura_activity import AuraActivityService


router = APIRouter(
    prefix="/aura",
    tags=["AURA"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/users/{external_id}/activity")
def aura_activity(external_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.external_id == external_id).one_or_none()
    if user is None:
        raise HTTPException(404, "AURA user not found")
    return AuraActivityService(db).snapshot(user)
