from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..horizon_scene_schemas import SceneObservation
from ..services.horizon_scene_analyzer import PublicSceneAnalyzer


router = APIRouter(tags=["HORIZON Public Scene Analyzer"])


@router.get("/horizon/public-scenes/cameras")
def public_scene_cameras(
    country: str | None = Query(default=None, min_length=2, max_length=2),
    nearby_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    nearby_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float = Query(default=50.0, ge=1.0, le=250.0),
    limit: int = Query(default=12, ge=1, le=50),
):
    if (nearby_lat is None) != (nearby_lon is None):
        raise HTTPException(
            status_code=400,
            detail="nearby_lat and nearby_lon must be provided together",
        )
    return PublicSceneAnalyzer().camera_registry(
        country=country,
        nearby_lat=nearby_lat,
        nearby_lon=nearby_lon,
        radius_km=radius_km,
        limit=limit,
    )


@router.get("/horizon/public-scenes/privacy-boundary")
def public_scene_privacy_boundary():
    return PublicSceneAnalyzer().privacy_boundary()


@router.post("/horizon/public-scenes/analyze")
def public_scene_analyze(payload: SceneObservation):
    return PublicSceneAnalyzer().analyze(payload)
