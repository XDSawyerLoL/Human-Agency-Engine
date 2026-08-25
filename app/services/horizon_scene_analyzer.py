from __future__ import annotations

from collections import Counter
import json
from math import hypot
import os
from statistics import mean, median
from typing import Any

import httpx

from ..horizon_scene_schemas import CameraRegistryItem, SceneDetection, SceneObservation


WINDY_WEBCAMS_ENDPOINT = "https://api.windy.com/webcams/api/v3/webcams"
WINDY_WEBCAMS_TERMS = "https://api.windy.com/webcams/terms"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _center(detection: SceneDetection) -> tuple[float, float]:
    return (
        min(1.0, max(0.0, detection.x + detection.width / 2.0)),
        min(1.0, max(0.0, detection.y + detection.height / 2.0)),
    )


def _speed(detection: SceneDetection) -> float | None:
    if detection.velocity_x is None or detection.velocity_y is None:
        return None
    return hypot(detection.velocity_x, detection.velocity_y)


def _nearest_neighbor_index(people: list[SceneDetection]) -> float | None:
    sample = people[:300]
    if len(sample) < 2:
        return None
    centers = [_center(item) for item in sample]
    nearest = []
    for index, (x1, y1) in enumerate(centers):
        closest = 2.0
        for other_index, (x2, y2) in enumerate(centers):
            if index == other_index:
                continue
            distance = hypot(x2 - x1, y2 - y1)
            if distance < closest:
                closest = distance
        nearest.append(closest)
    average_nearest = mean(nearest)
    # 0 = dispersed, 1 = very close clustering. This is a normalized scene heuristic,
    # not a social relationship inference.
    return max(0.0, min(1.0, 1.0 - average_nearest / 0.25))


def _first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _windy_camera(item: dict[str, Any]) -> CameraRegistryItem | None:
    webcam_id = item.get("webcamId")
    if webcam_id is None or item.get("status") not in {None, "active"}:
        return None

    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    images = item.get("images") if isinstance(item.get("images"), dict) else {}
    current = images.get("current") if isinstance(images.get("current"), dict) else {}
    player = item.get("player") if isinstance(item.get("player"), dict) else {}
    urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}

    preview_url = _first_text(current, ("preview", "small", "medium", "icon"))
    embed_url = _first_text(player, ("live", "day", "month", "year", "lifetime"))
    public_page_url = _first_text(urls, ("detail",))
    if not public_page_url:
        public_page_url = f"https://www.windy.com/webcams/{webcam_id}"

    title = str(item.get("title") or f"Windy webcam {webcam_id}").strip()
    place_parts = [
        str(location.get(key)).strip()
        for key in ("city", "region", "country")
        if location.get(key)
    ]
    location_label = " · ".join(dict.fromkeys(place_parts)) or "Localisation fournie par Windy"

    try:
        latitude = float(location["latitude"]) if location.get("latitude") is not None else None
        longitude = float(location["longitude"]) if location.get("longitude") is not None else None
    except (TypeError, ValueError):
        latitude = longitude = None

    return CameraRegistryItem(
        camera_id=f"windy:{webcam_id}",
        label=title,
        location_label=location_label,
        provider="Windy Webcams",
        public_page_url=public_page_url,
        preview_url=preview_url,
        embed_url=embed_url,
        latitude=latitude,
        longitude=longitude,
        display_authorized=True,
        # Windy's public API permits display/link/embed under its terms. That is not
        # treated as permission to run our computer-vision analytics over the feed.
        analysis_authorized=False,
        attribution="Webcams provided by Windy.com",
        terms_reference=WINDY_WEBCAMS_TERMS,
    )


class PublicSceneAnalyzer:
    ENGINE_VERSION = "horizon-public-scene-analyzer-v0.2"

    def __init__(self, *, timeout_seconds: float = 12.0):
        self.timeout_seconds = timeout_seconds

    def camera_registry(
        self,
        *,
        country: str | None = None,
        nearby_lat: float | None = None,
        nearby_lon: float | None = None,
        radius_km: float = 50.0,
        limit: int = 12,
    ) -> dict[str, Any]:
        cameras: list[dict[str, Any]] = []
        errors: list[str] = []
        provider_counts: Counter[str] = Counter()

        manual, manual_errors = self._manual_cameras()
        errors.extend(manual_errors)
        for camera in manual:
            cameras.append(camera.model_dump())
            provider_counts[camera.provider] += 1

        windy_key = os.getenv("HORIZON_WINDY_WEBCAMS_API_KEY", "").strip()
        windy_country = (country or os.getenv("HORIZON_PUBLIC_CAMERA_COUNTRY", "").strip()).upper() or None
        if windy_key:
            try:
                windy_cameras = self._windy_cameras(
                    api_key=windy_key,
                    country=windy_country,
                    nearby_lat=nearby_lat,
                    nearby_lon=nearby_lon,
                    radius_km=radius_km,
                    limit=max(1, min(int(limit), 50)),
                )
                existing_ids = {camera["camera_id"] for camera in cameras}
                for camera in windy_cameras:
                    if camera.camera_id in existing_ids:
                        continue
                    cameras.append(camera.model_dump())
                    provider_counts[camera.provider] += 1
                    existing_ids.add(camera.camera_id)
            except Exception as exc:
                errors.append(f"Windy Webcams: {str(exc)[:300]}")

        return {
            "engine": self.ENGINE_VERSION,
            "cameras": cameras[: max(1, min(int(limit), 50))],
            "configured_camera_count": len(cameras[: max(1, min(int(limit), 50))]),
            "provider_counts": dict(provider_counts),
            "errors": errors,
            "configuration": {
                "manual_registry_environment_variable": "HORIZON_PUBLIC_CAMERAS_JSON",
                "windy_api_key_environment_variable": "HORIZON_WINDY_WEBCAMS_API_KEY",
                "windy_country_environment_variable": "HORIZON_PUBLIC_CAMERA_COUNTRY",
                "windy_webcams_adapter_enabled": bool(windy_key),
                "windy_country_filter": windy_country,
                "requires_display_authorized": True,
                "analysis_requires_separate_authorization": True,
                "windy_image_urls_are_ephemeral": True,
            },
            "privacy_boundary": self.privacy_boundary(),
        }

    def _manual_cameras(self) -> tuple[list[CameraRegistryItem], list[str]]:
        raw = os.getenv("HORIZON_PUBLIC_CAMERAS_JSON", "").strip()
        cameras: list[CameraRegistryItem] = []
        errors: list[str] = []
        if not raw:
            return cameras, errors
        try:
            payload = json.loads(raw)
            if not isinstance(payload, list):
                raise ValueError("HORIZON_PUBLIC_CAMERAS_JSON must be a JSON list")
            for item in payload:
                try:
                    camera = CameraRegistryItem.model_validate(item)
                except Exception as exc:
                    errors.append(str(exc)[:300])
                    continue
                if camera.display_authorized:
                    cameras.append(camera)
        except Exception as exc:
            errors.append(str(exc)[:300])
        return cameras, errors

    def _windy_cameras(
        self,
        *,
        api_key: str,
        country: str | None,
        nearby_lat: float | None,
        nearby_lon: float | None,
        radius_km: float,
        limit: int,
    ) -> list[CameraRegistryItem]:
        params: dict[str, Any] = {
            "include": "images,location,player,urls",
            "lang": "fr",
            "limit": limit,
            "sortKey": "popularity",
            "sortDirection": "desc",
        }
        if nearby_lat is not None and nearby_lon is not None:
            params["nearby"] = (
                f"{float(nearby_lat):.6f},{float(nearby_lon):.6f},"
                f"{max(1.0, min(float(radius_km), 250.0)):.1f}"
            )
        elif country:
            params["countries"] = country

        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(
                WINDY_WEBCAMS_ENDPOINT,
                params=params,
                headers={"x-windy-api-key": api_key},
            )
            response.raise_for_status()
            payload = response.json()

        rows = []
        for item in payload.get("webcams") or []:
            if not isinstance(item, dict):
                continue
            camera = _windy_camera(item)
            if camera is not None:
                rows.append(camera)
        return rows

    def privacy_boundary(self) -> dict[str, Any]:
        return {
            "allowed": [
                "anonymous object counts",
                "crowd density and frame occupancy",
                "aggregate motion and direction",
                "anonymous dwell-time distributions",
                "zone occupancy",
                "queue-like or congestion-like scene heuristics",
            ],
            "forbidden_by_design": [
                "facial recognition",
                "identity lookup",
                "cross-camera re-identification",
                "persistent person tracking",
                "gait identification",
                "race or ethnicity inference",
                "religion or political affiliation inference",
                "sexual orientation inference",
                "health-status inference",
                "emotion or mental-state claims from faces",
            ],
            "raw_video_storage_required": False,
            "recommended_processing": "edge_or_ephemeral_then_aggregate",
        }

    def analyze(self, observation: SceneObservation) -> dict[str, Any]:
        counts = Counter(item.object_class for item in observation.detections)
        people = [item for item in observation.detections if item.object_class == "person"]
        vehicles = [
            item
            for item in observation.detections
            if item.object_class in {"bicycle", "motorcycle", "car", "bus", "truck"}
        ]

        person_occupancy = min(
            1.0,
            sum(min(1.0, item.width * item.height) for item in people),
        )
        all_occupancy = min(
            1.0,
            sum(min(1.0, item.width * item.height) for item in observation.detections),
        )

        moving_people = [(item, _speed(item)) for item in people]
        speed_values = [speed for _, speed in moving_people if speed is not None]
        stationary_people = [
            item
            for item, speed in moving_people
            if speed is not None and speed < 0.02
        ]
        stationary_share = (
            len(stationary_people) / len(speed_values) if speed_values else None
        )

        vectors = [
            (item.velocity_x, item.velocity_y)
            for item in people
            if item.velocity_x is not None
            and item.velocity_y is not None
            and hypot(item.velocity_x, item.velocity_y) > 0.005
        ]
        if vectors:
            mean_vx = mean(value[0] for value in vectors)
            mean_vy = mean(value[1] for value in vectors)
            mean_speed = mean(hypot(value[0], value[1]) for value in vectors)
            directional_coherence = min(
                1.0,
                hypot(mean_vx, mean_vy) / max(mean_speed, 1e-9),
            )
        else:
            mean_vx = mean_vy = 0.0
            mean_speed = None
            directional_coherence = None

        dwell_values = [
            float(item.dwell_seconds)
            for item in people
            if item.dwell_seconds is not None
        ]
        zone_counts = Counter(item.zone for item in people if item.zone)
        clustering_index = _nearest_neighbor_index(people)

        congestion_score = min(
            1.0,
            0.55 * person_occupancy
            + 0.25 * (stationary_share or 0.0)
            + 0.20 * (clustering_index or 0.0),
        )
        queue_like_score = min(
            1.0,
            0.40 * (stationary_share or 0.0)
            + 0.30 * min(1.0, (median(dwell_values) / 120.0) if dwell_values else 0.0)
            + 0.20 * (clustering_index or 0.0)
            + 0.10 * min(1.0, len(people) / 20.0),
        )

        if not people:
            scene_state = "no_people_detected"
        elif congestion_score >= 0.70:
            scene_state = "high_congestion"
        elif stationary_share is not None and stationary_share >= 0.65:
            scene_state = "mostly_stationary"
        elif mean_speed is not None and mean_speed >= 0.08 and (directional_coherence or 0.0) >= 0.55:
            scene_state = "coherent_flow"
        elif clustering_index is not None and clustering_index >= 0.65:
            scene_state = "aggregated"
        else:
            scene_state = "mixed_flow"

        signals = []
        if queue_like_score >= 0.65:
            signals.append(
                {
                    "type": "queue_like_pattern",
                    "score": round(queue_like_score, 4),
                    "claim": "Spatial and dwell-time features are compatible with a queue-like scene.",
                    "intent_inferred": False,
                }
            )
        if congestion_score >= 0.65:
            signals.append(
                {
                    "type": "congestion_like_pattern",
                    "score": round(congestion_score, 4),
                    "claim": "Occupancy, proximity and low motion are compatible with congestion.",
                    "intent_inferred": False,
                }
            )
        if directional_coherence is not None and directional_coherence >= 0.70 and len(vectors) >= 4:
            signals.append(
                {
                    "type": "coherent_directional_flow",
                    "score": round(directional_coherence, 4),
                    "claim": "Anonymous movement vectors show a common direction of travel.",
                    "intent_inferred": False,
                }
            )

        return {
            "engine": self.ENGINE_VERSION,
            "camera_id": observation.camera_id,
            "captured_at": observation.captured_at,
            "scene_state": scene_state,
            "counts": dict(counts),
            "people": {
                "count": len(people),
                "frame_occupancy": round(person_occupancy, 6),
                "clustering_index": round(clustering_index, 6)
                if clustering_index is not None
                else None,
                "stationary_share": round(stationary_share, 6)
                if stationary_share is not None
                else None,
                "dwell_seconds": {
                    "sample_count": len(dwell_values),
                    "median": round(median(dwell_values), 3) if dwell_values else None,
                    "p90": round(_percentile(dwell_values, 0.90), 3)
                    if dwell_values
                    else None,
                },
                "zone_counts": dict(zone_counts),
            },
            "vehicles": {
                "count": len(vehicles),
            },
            "motion": {
                "sample_count": len(speed_values),
                "mean_speed_normalized_per_second": round(mean(speed_values), 6)
                if speed_values
                else None,
                "mean_vector": {
                    "x": round(mean_vx, 6),
                    "y": round(mean_vy, 6),
                },
                "directional_coherence": round(directional_coherence, 6)
                if directional_coherence is not None
                else None,
            },
            "scene_metrics": {
                "all_object_frame_occupancy": round(all_occupancy, 6),
                "congestion_like_score": round(congestion_score, 6),
                "queue_like_score": round(queue_like_score, 6),
            },
            "behavioral_signals": signals,
            "privacy_boundary": self.privacy_boundary(),
            "critical_semantics": {
                "scene_pattern_is_personal_intent": False,
                "scene_pattern_is_emotion": False,
                "scene_pattern_identifies_people": False,
                "aggregate_metrics_can_feed_human_dynamics": True,
            },
        }
