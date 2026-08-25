from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ObjectClass = Literal["person", "bicycle", "motorcycle", "car", "bus", "truck", "other"]


class SceneDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_class: ObjectClass
    x: float = Field(..., ge=0.0, le=1.0, description="Normalized box left coordinate")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalized box top coordinate")
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    velocity_x: float | None = Field(default=None, ge=-5.0, le=5.0)
    velocity_y: float | None = Field(default=None, ge=-5.0, le=5.0)
    dwell_seconds: float | None = Field(default=None, ge=0.0, le=86400.0)
    zone: str | None = Field(default=None, max_length=80)


class SceneObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(..., min_length=1, max_length=160)
    captured_at: datetime
    frame_width: int = Field(..., ge=64, le=16384)
    frame_height: int = Field(..., ge=64, le=16384)
    detections: list[SceneDetection] = Field(default_factory=list, max_length=5000)
    source_latency_ms: float | None = Field(default=None, ge=0.0, le=600000.0)


class CameraRegistryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str = Field(..., min_length=1, max_length=160)
    label: str = Field(..., min_length=1, max_length=240)
    location_label: str = Field(..., min_length=1, max_length=240)
    provider: str = Field(..., min_length=1, max_length=160)
    public_page_url: str = Field(..., min_length=8, max_length=2000)
    preview_url: str | None = Field(default=None, max_length=4000)
    embed_url: str | None = Field(default=None, max_length=4000)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    display_authorized: bool = False
    analysis_authorized: bool = False
    terms_reference: str | None = Field(default=None, max_length=2000)
