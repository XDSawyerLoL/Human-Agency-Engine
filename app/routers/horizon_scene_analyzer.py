from __future__ import annotations

from fastapi import APIRouter

from ..horizon_scene_schemas import SceneObservation
from ..services.horizon_scene_analyzer import PublicSceneAnalyzer


router = APIRouter(tags=["HORIZON Public Scene Analyzer"])


@router.get("/horizon/public-scenes/cameras")
def public_scene_cameras():
    return PublicSceneAnalyzer().camera_registry()


@router.get("/horizon/public-scenes/privacy-boundary")
def public_scene_privacy_boundary():
    return PublicSceneAnalyzer().privacy_boundary()


@router.post("/horizon/public-scenes/analyze")
def public_scene_analyze(payload: SceneObservation):
    return PublicSceneAnalyzer().analyze(payload)
