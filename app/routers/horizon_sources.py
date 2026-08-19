from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_source_models import HorizonEventCandidate, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from ..security import require_api_key
from ..services.horizon_sources import HorizonSourceService

router = APIRouter(prefix="/horizon/sources", dependencies=[Depends(require_api_key)])


def _source_or_404(db: Session, source_key: str) -> HorizonSource:
    row = db.query(HorizonSource).filter(HorizonSource.source_key == source_key).one_or_none()
    if not row:
        raise HTTPException(404, "HORIZON source not found")
    return row


@router.post("/builtins/sync")
def sync_builtin_sources(db: Session = Depends(get_db)):
    rows = HorizonSourceService(db).sync_builtin_sources()
    return {
        "sources": [
            {
                "source_key": row.source_key,
                "name": row.name,
                "source_class": row.source_class,
                "adapter_kind": row.adapter_kind,
                "requires_credentials": row.requires_credentials,
                "enabled": row.enabled,
            }
            for row in rows
        ]
    }


@router.put("")
def upsert_source(payload: HorizonSourceUpsert, db: Session = Depends(get_db)):
    row = HorizonSourceService(db).upsert_source(payload)
    return {
        "source_key": row.source_key,
        "name": row.name,
        "source_class": row.source_class,
        "adapter_kind": row.adapter_kind,
        "domains": row.domains,
        "geography": row.geography,
        "trust_weight": row.trust_weight,
        "trust_weight_is_probability": False,
        "refresh_seconds": row.refresh_seconds,
        "requires_credentials": row.requires_credentials,
        "enabled": row.enabled,
        "metadata": row.metadata_json,
    }


@router.get("")
def list_sources(enabled_only: bool = Query(default=False), db: Session = Depends(get_db)):
    query = db.query(HorizonSource)
    if enabled_only:
        query = query.filter(HorizonSource.enabled == True)  # noqa: E712
    rows = query.order_by(HorizonSource.source_class.asc(), HorizonSource.source_key.asc()).all()
    return [
        {
            "source_key": row.source_key,
            "name": row.name,
            "source_class": row.source_class,
            "adapter_kind": row.adapter_kind,
            "domains": row.domains,
            "geography": row.geography,
            "trust_weight": row.trust_weight,
            "trust_weight_is_probability": False,
            "refresh_seconds": row.refresh_seconds,
            "requires_credentials": row.requires_credentials,
            "enabled": row.enabled,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]


@router.post("/{source_key}/observations")
def ingest_observation(
    source_key: str,
    payload: HorizonObservationIngest,
    db: Session = Depends(get_db),
):
    source = _source_or_404(db, source_key)
    try:
        row, created = HorizonSourceService(db).ingest_observation(source, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "id": row.id,
        "created": created,
        "source_key": source.source_key,
        "source_class": source.source_class,
        "external_key": row.external_key,
        "observation_type": row.observation_type,
        "payload_hash": row.payload_hash,
        "observed_at": row.observed_at,
        "immutable_observation": True,
    }


@router.post("/candidates")
def build_candidate(payload: HorizonCandidateBuild, db: Session = Depends(get_db)):
    try:
        row = HorizonSourceService(db).build_candidate(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    readiness = HorizonSourceService(db).promotion_readiness(row)
    return {
        "id": row.id,
        "candidate_key": row.candidate_key,
        "event_type": row.event_type,
        "title": row.title,
        "geography": row.geography,
        "observation_ids": row.corroborating_observation_ids,
        "source_classes": row.source_classes,
        "corroboration_score": row.corroboration_score,
        "corroboration_score_is_probability": False,
        "promotion_status": row.promotion_status,
        "promotion_readiness": readiness,
        "first_observed_at": row.first_observed_at,
        "last_observed_at": row.last_observed_at,
    }


@router.post("/candidates/{candidate_id}/promote")
def promote_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(HorizonEventCandidate).filter(HorizonEventCandidate.id == candidate_id).one_or_none()
    if not candidate:
        raise HTTPException(404, "HORIZON event candidate not found")
    try:
        event = HorizonSourceService(db).promote_candidate(candidate)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "candidate_id": candidate.id,
        "event_id": event.id,
        "event_key": event.event_key,
        "event_type": event.event_type,
        "title": event.title,
        "source": event.source,
        "source_reliability": event.source_reliability,
        "raw_facts": event.raw_facts,
        "promoted": True,
    }


from .agency import router as agency_router  # noqa: E402

agency_router.include_router(router)
