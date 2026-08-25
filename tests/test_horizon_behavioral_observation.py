from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.horizon_behavioral_knowledge_schemas import BehavioralKnowledgeSearchRequest
from app.horizon_scene_schemas import SceneDetection, SceneObservation
from app.services.horizon_behavioral_knowledge import BehavioralKnowledgeService
from app.services.horizon_scene_analyzer import PublicSceneAnalyzer, _windy_camera


def test_behavioral_source_catalog_separates_runtime_and_licensed_archives():
    catalog = BehavioralKnowledgeService().source_catalog()
    by_key = {item["key"]: item for item in catalog["sources"]}

    assert by_key["openalex"]["runtime_adapter"] is True
    assert by_key["pubmed"]["runtime_adapter"] is True
    assert by_key["wvs"]["automated_fulltext_ingestion"] is False
    assert by_key["ess"]["automated_fulltext_ingestion"] is False
    assert catalog["principles"]["citation_count_is_not_replication_quality"] is True


def test_behavioral_search_schema_rejects_unknown_sources():
    with pytest.raises(ValidationError):
        BehavioralKnowledgeSearchRequest(query="conformity behavior", sources=["unknown"])


def test_scene_analyzer_reports_aggregate_flow_without_identity_claims():
    observation = SceneObservation(
        camera_id="demo-public-scene",
        captured_at=datetime.now(timezone.utc),
        frame_width=1920,
        frame_height=1080,
        detections=[
            SceneDetection(
                object_class="person",
                x=0.10,
                y=0.30,
                width=0.04,
                height=0.16,
                velocity_x=0.08,
                velocity_y=0.01,
                dwell_seconds=8,
                zone="walkway",
            ),
            SceneDetection(
                object_class="person",
                x=0.18,
                y=0.31,
                width=0.04,
                height=0.16,
                velocity_x=0.09,
                velocity_y=0.00,
                dwell_seconds=11,
                zone="walkway",
            ),
            SceneDetection(
                object_class="person",
                x=0.26,
                y=0.32,
                width=0.04,
                height=0.16,
                velocity_x=0.10,
                velocity_y=0.01,
                dwell_seconds=7,
                zone="walkway",
            ),
            SceneDetection(
                object_class="person",
                x=0.34,
                y=0.33,
                width=0.04,
                height=0.16,
                velocity_x=0.08,
                velocity_y=0.00,
                dwell_seconds=9,
                zone="walkway",
            ),
        ],
    )

    result = PublicSceneAnalyzer().analyze(observation)

    assert result["counts"]["person"] == 4
    assert result["motion"]["directional_coherence"] > 0.9
    assert result["critical_semantics"]["scene_pattern_identifies_people"] is False
    assert "facial recognition" in result["privacy_boundary"]["forbidden_by_design"]


def test_scene_schema_forbids_biometric_fields():
    with pytest.raises(ValidationError):
        SceneDetection.model_validate(
            {
                "object_class": "person",
                "x": 0.1,
                "y": 0.1,
                "width": 0.1,
                "height": 0.2,
                "face_embedding": [0.1, 0.2, 0.3],
            }
        )


def test_camera_registry_only_returns_explicitly_authorized_entries(monkeypatch):
    monkeypatch.delenv("HORIZON_WINDY_WEBCAMS_API_KEY", raising=False)
    monkeypatch.setenv(
        "HORIZON_PUBLIC_CAMERAS_JSON",
        """[
          {
            "camera_id": "allowed",
            "label": "Authorized public webcam",
            "location_label": "Example",
            "provider": "official-provider",
            "public_page_url": "https://example.org/camera",
            "preview_url": "https://example.org/preview.jpg",
            "display_authorized": true,
            "analysis_authorized": false
          },
          {
            "camera_id": "not-allowed",
            "label": "Not authorized",
            "location_label": "Example",
            "provider": "other-provider",
            "public_page_url": "https://example.org/private-display",
            "display_authorized": false,
            "analysis_authorized": false
          }
        ]""",
    )

    registry = PublicSceneAnalyzer().camera_registry()

    assert registry["configured_camera_count"] == 1
    assert registry["cameras"][0]["camera_id"] == "allowed"


def test_windy_camera_mapping_never_grants_analysis_permission():
    camera = _windy_camera(
        {
            "webcamId": 1358084658,
            "status": "active",
            "title": "Public square",
            "images": {
                "current": {
                    "preview": "https://images.windy.example/tokenized-preview.jpg"
                }
            },
            "location": {
                "city": "Paris",
                "region": "Île-de-France",
                "country": "France",
                "latitude": 48.8566,
                "longitude": 2.3522,
            },
            "player": {
                "live": "https://webcams.windy.example/embed/live/1358084658"
            },
            "urls": {
                "detail": "https://www.windy.com/webcams/1358084658"
            },
        }
    )

    assert camera is not None
    assert camera.camera_id == "windy:1358084658"
    assert camera.display_authorized is True
    assert camera.analysis_authorized is False
    assert camera.attribution == "Webcams provided by Windy.com"
    assert camera.preview_url.endswith("tokenized-preview.jpg")
