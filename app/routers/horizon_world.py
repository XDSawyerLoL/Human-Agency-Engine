from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import require_api_key
from ..horizon_supply_trigger_schemas import HorizonGdeltFuelSupplyTriggerBackfillRequest
from ..services.horizon_world_coverage import HorizonWorldCoverageService
from ..services.horizon_mechanism_registry import HorizonMechanismRegistryService
from ..services.horizon_gdelt1_supply_trigger import HorizonGdeltFuelSupplyTriggerBackfillService


router = APIRouter(prefix="/horizon/world", dependencies=[Depends(require_api_key)])


@router.get("/coverage")
def world_coverage(db: Session = Depends(get_db)):
    return HorizonWorldCoverageService(db).snapshot()


@router.get("/mechanisms")
def world_mechanisms(db: Session = Depends(get_db)):
    return HorizonMechanismRegistryService(db).snapshot()


@router.post("/backfill/fuel-supply-trigger")
def backfill_fuel_supply_trigger(
    payload: HorizonGdeltFuelSupplyTriggerBackfillRequest,
    db: Session = Depends(get_db),
):
    try:
        return HorizonGdeltFuelSupplyTriggerBackfillService(db).backfill(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
