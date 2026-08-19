from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..services.horizon_response_library import HorizonResponseLibraryService, LIBRARY_VERSION

router = APIRouter(prefix="/horizon/response-library", dependencies=[Depends(require_api_key)])


def _out(row):
    return {
        "id": row.id,
        "pattern_key": row.pattern_key,
        "name": row.name,
        "event_types": row.event_types,
        "predicted_response": row.predicted_response,
        "mechanism_chain": row.mechanism_chain,
        "expected_lag_hours_low": row.expected_lag_hours_low,
        "expected_lag_hours_high": row.expected_lag_hours_high,
        "confidence": row.confidence,
        "confidence_is_probability": False,
        "support_count": row.support_count,
        "contradiction_count": row.contradiction_count,
        "knowledge_available_at": row.knowledge_available_at,
        "provenance": row.provenance,
        "status": row.status,
    }


@router.post("/builtins/sync")
def sync_builtin_response_patterns(db: Session = Depends(get_db)):
    try:
        rows = HorizonResponseLibraryService(db).sync_builtins()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "library_version": LIBRARY_VERSION,
        "patterns": [_out(row) for row in rows],
        "formal_probabilities": False,
        "horizon_support_counts_are_real_labels_only": True,
    }


@router.get("/builtins")
def list_builtin_response_patterns(db: Session = Depends(get_db)):
    rows = HorizonResponseLibraryService(db).list_builtins()
    return {
        "library_version": LIBRARY_VERSION,
        "patterns": [_out(row) for row in rows],
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
