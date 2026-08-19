from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_live_models import HorizonLiveSource
from ..security import require_api_key
from ..services.horizon_live import HorizonLiveIngestionService

router = APIRouter(prefix="/horizon/live", dependencies=[Depends(require_api_key)])


@router.get("/sources")
def list_live_sources(db: Session = Depends(get_db)):
    rows = db.query(HorizonLiveSource).order_by(HorizonLiveSource.source_key.asc()).all()
    return [
        {
            "source_key": row.source_key,
            "name": row.name,
            "source_kind": row.source_kind,
            "endpoint": row.endpoint,
            "enabled": row.enabled,
            "last_started_at": row.last_started_at,
            "last_success_at": row.last_success_at,
            "last_error": row.last_error,
        }
        for row in rows
    ]


@router.post("/sync")
def sync_all_live_sources(db: Session = Depends(get_db)):
    return HorizonLiveIngestionService(db).sync_all()


@router.post("/sources/{source_key}/sync")
def sync_one_live_source(source_key: str, db: Session = Depends(get_db)):
    service = HorizonLiveIngestionService(db)
    adapter = next((item for item in service.adapters() if item.source_key == source_key), None)
    if adapter is None:
        raise HTTPException(404, "HORIZON live source not configured")
    try:
        return service.sync_adapter(adapter)
    except Exception as exc:
        raise HTTPException(502, f"HORIZON live source sync failed: {exc}") from exc


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
