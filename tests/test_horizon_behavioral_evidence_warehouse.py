from __future__ import annotations

from uuid import uuid4

from app.db import SessionLocal
from app.horizon_behavioral_warehouse_models import (
    HorizonBehavioralDocument,
    HorizonBehavioralEffect,
    HorizonBehavioralIngestionRun,
)
from app.horizon_behavioral_warehouse_schemas import (
    BehavioralEffectCreate,
    BehavioralEffectReview,
    BehavioralWarehouseCalibrationPackRequest,
    BehavioralWarehouseHarvestRequest,
)
from app.services.horizon_behavioral_warehouse import BehavioralEvidenceWarehouseService


class FakeKnowledgeService:
    def search(self, request):  # noqa: ARG002
        return {
            "results": [
                {
                    "source": "openalex",
                    "record_id": "https://openalex.org/W123456789",
                    "title": "Social norms and behavioral adoption",
                    "publication_year": 2024,
                    "publication_date": "2024-02-10",
                    "work_type": "article",
                    "doi": "https://doi.org/10.1234/example",
                    "venue": "Behavior Journal",
                    "cited_by_count": 42,
                    "open_access": True,
                    "open_access_url": "https://example.org/paper",
                    "abstract": "This abstract is intentionally not persisted by the warehouse.",
                    "topics": ["Social Norm", "Behavior"],
                    "evidence_signal": 0.72,
                }
            ],
            "errors": [],
        }


def _cleanup(db):
    db.query(HorizonBehavioralEffect).delete(synchronize_session=False)
    db.query(HorizonBehavioralDocument).delete(synchronize_session=False)
    db.query(HorizonBehavioralIngestionRun).delete(synchronize_session=False)
    db.commit()


def _effect_payload(document_key: str, *, construct: str = "social_norm_support") -> BehavioralEffectCreate:
    return BehavioralEffectCreate(
        document_key=document_key,
        mechanism="social",
        construct=construct,
        population="urban adults",
        context="adoption of a visible public behavior",
        exposure="peer compliance is visible",
        behavioral_outcome="adoption of the target behavior",
        effect_direction="positive",
        effect_size=0.31,
        effect_size_type="standardized_mean_difference",
        uncertainty_low=0.20,
        uncertainty_high=0.42,
        sample_size=1200,
        study_design="randomized_experiment",
        replication_status="replicated",
        preregistered=True,
        peer_reviewed=True,
        countries=["FR"],
        time_horizon="within 7 days",
        evidence_summary="Visible peer compliance increased adoption in the studied setting.",
        source_locator="results/table-2",
        extraction_method="human",
        extraction_version="test-v1",
        extraction_confidence=0.95,
    )


def test_harvest_is_idempotent_and_does_not_persist_abstract_text():
    db = SessionLocal()
    _cleanup(db)
    service = BehavioralEvidenceWarehouseService(db, knowledge_service=FakeKnowledgeService())
    request = BehavioralWarehouseHarvestRequest(
        query="social norms adoption",
        sources=["openalex"],
        limit_per_source=5,
    )
    try:
        first = service.harvest(request)
        second = service.harvest(request)

        assert first["documents_created"] == 1
        assert first["documents_updated"] == 0
        assert second["documents_created"] == 0
        assert second["documents_updated"] == 1
        assert db.query(HorizonBehavioralDocument).count() == 1

        document = db.query(HorizonBehavioralDocument).one()
        assert document.abstract_available is True
        assert "abstract" not in document.metadata_snapshot
        assert document.ingestion_count == 2
        assert first["storage_semantics"]["abstract_text_persisted"] is False
    finally:
        _cleanup(db)
        db.close()


def test_candidate_effect_cannot_enter_calibration_pack_until_reviewed():
    db = SessionLocal()
    _cleanup(db)
    service = BehavioralEvidenceWarehouseService(db, knowledge_service=FakeKnowledgeService())
    try:
        harvest = service.harvest(
            BehavioralWarehouseHarvestRequest(
                query="social norms adoption",
                sources=["openalex"],
                limit_per_source=5,
            )
        )
        document_key = harvest["documents"][0]["document_key"]
        created = service.add_effect(_effect_payload(document_key))

        assert created["created"] is True
        assert created["effect"]["evidence_status"] == "candidate"
        assert created["effect"]["quality_score"] > 0.75

        before = service.calibration_pack(
            BehavioralWarehouseCalibrationPackRequest(
                mechanisms=["social"],
                min_quality_score=0.4,
                min_effects_per_mechanism=1,
            )
        )
        assert before["accepted_effects_considered"] == 0

        reviewed = service.review_effect(
            created["effect"]["effect_key"],
            BehavioralEffectReview(
                status="accepted",
                reviewed_by="test-reviewer",
                notes="Methods and outcome fields checked.",
            ),
        )
        assert reviewed["eligible_for_calibration_export"] is True

        after = service.calibration_pack(
            BehavioralWarehouseCalibrationPackRequest(
                mechanisms=["social"],
                min_quality_score=0.4,
                min_effects_per_mechanism=1,
                countries=["FR"],
            )
        )
        assert after["accepted_effects_considered"] == 1
        assert after["mechanisms"][0]["mechanism"] == "social"
        assert after["mechanisms"][0]["evidence_direction_index"] > 0
        assert after["mechanisms"][0]["eligible_for_learning"] is True
        assert after["semantics"]["automatically_changes_human_dynamics_coefficients"] is False
    finally:
        _cleanup(db)
        db.close()


def test_duplicate_effect_extraction_is_idempotent():
    db = SessionLocal()
    _cleanup(db)
    service = BehavioralEvidenceWarehouseService(db, knowledge_service=FakeKnowledgeService())
    try:
        harvest = service.harvest(
            BehavioralWarehouseHarvestRequest(
                query="social norms adoption",
                sources=["openalex"],
                limit_per_source=5,
            )
        )
        payload = _effect_payload(harvest["documents"][0]["document_key"])
        first = service.add_effect(payload)
        second = service.add_effect(payload)

        assert first["created"] is True
        assert second["created"] is False
        assert first["effect"]["effect_key"] == second["effect"]["effect_key"]
        assert db.query(HorizonBehavioralEffect).count() == 1
    finally:
        _cleanup(db)
        db.close()


def test_rejected_effect_never_enters_calibration_pack():
    db = SessionLocal()
    _cleanup(db)
    service = BehavioralEvidenceWarehouseService(db, knowledge_service=FakeKnowledgeService())
    try:
        harvest = service.harvest(
            BehavioralWarehouseHarvestRequest(
                query=f"behavior test {uuid4().hex[:8]}",
                sources=["openalex"],
                limit_per_source=5,
            )
        )
        created = service.add_effect(_effect_payload(harvest["documents"][0]["document_key"]))
        service.review_effect(
            created["effect"]["effect_key"],
            BehavioralEffectReview(
                status="rejected",
                reviewed_by="test-reviewer",
                notes="Outcome extraction did not match the source.",
            ),
        )

        pack = service.calibration_pack(
            BehavioralWarehouseCalibrationPackRequest(
                mechanisms=["social"],
                min_quality_score=0.0,
                min_effects_per_mechanism=1,
            )
        )
        assert pack["accepted_effects_considered"] == 0
        assert pack["mechanisms"] == []
    finally:
        _cleanup(db)
        db.close()
