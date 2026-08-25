from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..horizon_behavioral_warehouse_schemas import (
    BehavioralEffectCreate,
    BehavioralEffectReview,
    BehavioralWarehouseBootstrapRequest,
    BehavioralWarehouseCalibrationPackRequest,
    BehavioralWarehouseHarvestRequest,
)
from ..security import require_api_key
from ..services.horizon_behavioral_warehouse import BehavioralEvidenceWarehouseService


router = APIRouter(tags=["HORIZON Behavioral Evidence Warehouse"])


@router.get("/horizon/behavioral-warehouse/status")
def behavioral_warehouse_status(db: Session = Depends(get_db)):
    return BehavioralEvidenceWarehouseService(db).status()


@router.post(
    "/horizon/behavioral-warehouse/harvest",
    dependencies=[Depends(require_api_key)],
)
def behavioral_warehouse_harvest(
    payload: BehavioralWarehouseHarvestRequest,
    db: Session = Depends(get_db),
):
    return BehavioralEvidenceWarehouseService(db).harvest(payload)


@router.post(
    "/horizon/behavioral-warehouse/bootstrap",
    dependencies=[Depends(require_api_key)],
)
def behavioral_warehouse_bootstrap(
    payload: BehavioralWarehouseBootstrapRequest,
    db: Session = Depends(get_db),
):
    return BehavioralEvidenceWarehouseService(db).bootstrap(payload)


@router.get("/horizon/behavioral-warehouse/documents")
def behavioral_warehouse_documents(
    source: str | None = Query(default=None, max_length=48),
    publication_year_from: int | None = Query(default=None, ge=1800, le=2200),
    evidence_status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return BehavioralEvidenceWarehouseService(db).documents(
        source=source,
        publication_year_from=publication_year_from,
        evidence_status=evidence_status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/horizon/behavioral-warehouse/effects",
    dependencies=[Depends(require_api_key)],
)
def behavioral_warehouse_add_effect(
    payload: BehavioralEffectCreate,
    db: Session = Depends(get_db),
):
    try:
        return BehavioralEvidenceWarehouseService(db).add_effect(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/horizon/behavioral-warehouse/effects/{effect_key}/review",
    dependencies=[Depends(require_api_key)],
)
def behavioral_warehouse_review_effect(
    effect_key: str,
    payload: BehavioralEffectReview,
    db: Session = Depends(get_db),
):
    try:
        return BehavioralEvidenceWarehouseService(db).review_effect(effect_key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/horizon/behavioral-warehouse/effects")
def behavioral_warehouse_effects(
    mechanism: str | None = Query(default=None, max_length=48),
    evidence_status: str | None = Query(default=None, max_length=32),
    min_quality_score: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return BehavioralEvidenceWarehouseService(db).effects(
        mechanism=mechanism,
        evidence_status=evidence_status,
        min_quality_score=min_quality_score,
        limit=limit,
        offset=offset,
    )


@router.post("/horizon/behavioral-warehouse/calibration-pack")
def behavioral_warehouse_calibration_pack(
    payload: BehavioralWarehouseCalibrationPackRequest,
    db: Session = Depends(get_db),
):
    return BehavioralEvidenceWarehouseService(db).calibration_pack(payload)
