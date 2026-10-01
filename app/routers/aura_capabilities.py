from __future__ import annotations

from fastapi import APIRouter

from ..services.aura_capability_registry import build_aura_capability_registry


router = APIRouter(prefix="/aura", tags=["AURA"])


@router.get("/capabilities")
def aura_capabilities():
    """Public-safe truth surface for what AURA can and cannot do right now."""
    return build_aura_capability_registry()


@router.get("/capabilities/summary")
def aura_capabilities_summary():
    registry = build_aura_capability_registry()
    return {
        "registry": registry["registry"],
        "generated_at": registry["generated_at"],
        "truth_policy": registry["truth_policy"],
        "summary": registry["summary"],
    }
