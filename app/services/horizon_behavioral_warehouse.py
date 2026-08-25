from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
import math
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..horizon_behavioral_knowledge_schemas import BehavioralKnowledgeSearchRequest
from ..horizon_behavioral_warehouse_models import (
    HorizonBehavioralDocument,
    HorizonBehavioralEffect,
    HorizonBehavioralIngestionRun,
)
from ..horizon_behavioral_warehouse_schemas import (
    BehavioralEffectCreate,
    BehavioralEffectReview,
    BehavioralWarehouseBootstrapRequest,
    BehavioralWarehouseCalibrationPackRequest,
    BehavioralWarehouseHarvestRequest,
)
from .horizon_behavioral_knowledge import BehavioralKnowledgeService, MECHANISM_QUERIES


DESIGN_SCORE = {
    "meta_analysis": 1.00,
    "systematic_review": 0.90,
    "randomized_experiment": 0.95,
    "quasi_experimental": 0.78,
    "longitudinal": 0.72,
    "observational": 0.58,
    "cross_sectional": 0.48,
    "qualitative": 0.38,
    "simulation": 0.35,
    "unknown": 0.25,
}

REPLICATION_SCORE = {
    "replicated": 1.00,
    "mixed": 0.62,
    "failed": 0.18,
    "not_applicable": 0.65,
    "unknown": 0.40,
}

DIRECTION_VALUE = {
    "positive": 1.0,
    "negative": -1.0,
    "null": 0.0,
    "mixed": 0.0,
    "unknown": 0.0,
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def _document_key(source: str, source_record_id: str) -> str:
    return f"bdoc_{sha256(f'{source}:{source_record_id}'.encode()).hexdigest()[:32]}"


def _effect_key(payload: BehavioralEffectCreate) -> str:
    identity = {
        "document_key": payload.document_key,
        "mechanism": payload.mechanism,
        "construct": payload.construct.strip().lower(),
        "population": payload.population.strip().lower(),
        "context": payload.context.strip().lower(),
        "outcome": payload.behavioral_outcome.strip().lower(),
        "effect_direction": payload.effect_direction,
        "effect_size": payload.effect_size,
        "effect_size_type": payload.effect_size_type,
        "source_locator": payload.source_locator,
    }
    return f"beff_{_stable_hash(identity)[:32]}"


def _quality_score(payload: BehavioralEffectCreate) -> float:
    design = DESIGN_SCORE.get(payload.study_design, DESIGN_SCORE["unknown"])
    replication = REPLICATION_SCORE.get(
        payload.replication_status,
        REPLICATION_SCORE["unknown"],
    )
    if payload.sample_size:
        sample = min(1.0, math.log10(payload.sample_size + 1) / 4.0)
    else:
        sample = 0.2
    preregistration = 1.0 if payload.preregistered is True else 0.45 if payload.preregistered is None else 0.0
    peer_review = 1.0 if payload.peer_reviewed is True else 0.45 if payload.peer_reviewed is None else 0.0
    effect_completeness = 1.0 if payload.effect_size is not None and payload.effect_size_type else 0.35
    quality = (
        0.35 * design
        + 0.20 * replication
        + 0.15 * sample
        + 0.08 * preregistration
        + 0.05 * peer_review
        + 0.07 * effect_completeness
        + 0.10 * payload.extraction_confidence
    )
    if payload.effect_direction == "unknown":
        quality *= 0.85
    return round(max(0.0, min(1.0, quality)), 6)


def _serialize_document(row: HorizonBehavioralDocument) -> dict[str, Any]:
    return {
        "document_key": row.document_key,
        "source": row.source,
        "source_record_id": row.source_record_id,
        "doi": row.doi,
        "title": row.title,
        "publication_year": row.publication_year,
        "publication_date": row.publication_date,
        "work_type": row.work_type,
        "venue": row.venue,
        "open_access": row.open_access,
        "canonical_url": row.canonical_url,
        "topics": row.topics or [],
        "discovery_signal": row.discovery_signal,
        "discovery_signal_is_scientific_validity_probability": False,
        "abstract_available": row.abstract_available,
        "ingestion_count": row.ingestion_count,
        "evidence_status": row.evidence_status,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
    }


def _serialize_effect(row: HorizonBehavioralEffect, document: HorizonBehavioralDocument | None = None) -> dict[str, Any]:
    return {
        "effect_key": row.effect_key,
        "document_key": document.document_key if document else None,
        "source": document.source if document else None,
        "title": document.title if document else None,
        "publication_year": document.publication_year if document else None,
        "mechanism": row.mechanism,
        "construct": row.construct,
        "population": row.population,
        "context": row.context,
        "exposure": row.exposure,
        "behavioral_outcome": row.behavioral_outcome,
        "effect_direction": row.effect_direction,
        "effect_size": row.effect_size,
        "effect_size_type": row.effect_size_type,
        "uncertainty_low": row.uncertainty_low,
        "uncertainty_high": row.uncertainty_high,
        "sample_size": row.sample_size,
        "study_design": row.study_design,
        "replication_status": row.replication_status,
        "preregistered": row.preregistered,
        "peer_reviewed": row.peer_reviewed,
        "countries": row.countries or [],
        "time_horizon": row.time_horizon,
        "evidence_summary": row.evidence_summary,
        "source_locator": row.source_locator,
        "extraction_method": row.extraction_method,
        "extraction_version": row.extraction_version,
        "extraction_confidence": row.extraction_confidence,
        "quality_score": row.quality_score,
        "quality_score_is_probability_effect_is_true": False,
        "evidence_status": row.evidence_status,
        "review_notes": row.review_notes,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class BehavioralEvidenceWarehouseService:
    ENGINE_VERSION = "horizon-behavioral-evidence-warehouse-v1.0"

    def __init__(self, db: Session, *, knowledge_service: BehavioralKnowledgeService | None = None):
        self.db = db
        self.knowledge = knowledge_service or BehavioralKnowledgeService()

    def status(self) -> dict[str, Any]:
        documents = self.db.query(HorizonBehavioralDocument).count()
        effects = self.db.query(HorizonBehavioralEffect).count()
        accepted = self.db.query(HorizonBehavioralEffect).filter_by(evidence_status="accepted").count()
        candidates = self.db.query(HorizonBehavioralEffect).filter_by(evidence_status="candidate").count()
        rejected = self.db.query(HorizonBehavioralEffect).filter_by(evidence_status="rejected").count()
        sources = [
            source
            for (source,) in self.db.query(HorizonBehavioralDocument.source).distinct().all()
        ]
        mechanisms = [
            mechanism
            for (mechanism,) in self.db.query(HorizonBehavioralEffect.mechanism).distinct().all()
        ]
        return {
            "engine": self.ENGINE_VERSION,
            "documents": documents,
            "effects": {
                "total": effects,
                "candidate": candidates,
                "accepted": accepted,
                "rejected": rejected,
            },
            "sources": sorted(sources),
            "mechanisms": sorted(mechanisms),
            "learning_gate": {
                "discovered_documents_change_human_dynamics": False,
                "candidate_effects_change_human_dynamics": False,
                "accepted_effects_are_eligible_for_calibration_export": True,
                "calibration_export_automatically_changes_coefficients": False,
            },
        }

    def harvest(self, payload: BehavioralWarehouseHarvestRequest) -> dict[str, Any]:
        run = HorizonBehavioralIngestionRun(
            run_key=f"bwh_{uuid4().hex}",
            query=payload.query,
            sources=list(payload.sources),
            request_snapshot=payload.model_dump(mode="json"),
            status="running",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            search = self.knowledge.search(
                BehavioralKnowledgeSearchRequest(
                    query=payload.query,
                    sources=list(payload.sources),
                    limit_per_source=payload.limit_per_source,
                    publication_year_from=payload.publication_year_from,
                    publication_year_to=payload.publication_year_to,
                    open_access_only=payload.open_access_only,
                )
            )
            created = 0
            updated = 0
            documents = []
            now = _utcnow()
            for result in search.get("results") or []:
                source = str(result.get("source") or "unknown")[:48]
                record_id = str(result.get("record_id") or result.get("doi") or "").strip()
                if not record_id:
                    record_id = f"fallback:{_stable_hash([result.get('title'), result.get('publication_year'), result.get('venue')])[:32]}"
                row = (
                    self.db.query(HorizonBehavioralDocument)
                    .filter_by(source=source, source_record_id=record_id)
                    .one_or_none()
                )
                metadata_snapshot = {
                    "doi": result.get("doi"),
                    "publication_year": result.get("publication_year"),
                    "publication_date": result.get("publication_date"),
                    "work_type": result.get("work_type"),
                    "venue": result.get("venue"),
                    "cited_by_count": result.get("cited_by_count"),
                    "open_access": result.get("open_access"),
                    "open_access_url": result.get("open_access_url"),
                    "topics": result.get("topics") or [],
                    "evidence_signal": result.get("evidence_signal"),
                }
                fingerprint = _stable_hash(
                    {
                        "source": source,
                        "record_id": record_id,
                        "title": result.get("title"),
                        "metadata": metadata_snapshot,
                    }
                )
                canonical_url = result.get("open_access_url") or result.get("doi")
                if source == "pubmed" and record_id.startswith("pmid:"):
                    canonical_url = f"https://pubmed.ncbi.nlm.nih.gov/{record_id.split(':', 1)[1]}/"
                values = {
                    "doi": (str(result.get("doi"))[:512] if result.get("doi") else None),
                    "title": str(result.get("title") or "Untitled behavioral record"),
                    "publication_year": result.get("publication_year"),
                    "publication_date": (str(result.get("publication_date"))[:32] if result.get("publication_date") else None),
                    "work_type": (str(result.get("work_type"))[:256] if result.get("work_type") else None),
                    "venue": (str(result.get("venue")) if result.get("venue") else None),
                    "open_access": result.get("open_access"),
                    "canonical_url": (str(canonical_url) if canonical_url else None),
                    "topics": list(result.get("topics") or []),
                    "discovery_signal": result.get("evidence_signal"),
                    "abstract_available": bool(result.get("abstract")),
                    "metadata_snapshot": metadata_snapshot,
                    "content_fingerprint": fingerprint,
                    "last_seen_at": now,
                    "updated_at": now,
                }
                if row is None:
                    row = HorizonBehavioralDocument(
                        document_key=_document_key(source, record_id),
                        source=source,
                        source_record_id=record_id[:512],
                        first_seen_at=now,
                        created_at=now,
                        **values,
                    )
                    self.db.add(row)
                    created += 1
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.ingestion_count += 1
                    updated += 1
                documents.append(row)

            run.documents_seen = len(search.get("results") or [])
            run.documents_created = created
            run.documents_updated = updated
            run.errors = search.get("errors") or []
            run.status = "completed_with_errors" if run.errors else "completed"
            run.completed_at = _utcnow()
            run.result_snapshot = {
                "results_returned": run.documents_seen,
                "documents_created": created,
                "documents_updated": updated,
                "abstract_text_persisted": False,
            }
            self.db.commit()

            return {
                "engine": self.ENGINE_VERSION,
                "run_key": run.run_key,
                "query": payload.query,
                "status": run.status,
                "documents_seen": run.documents_seen,
                "documents_created": created,
                "documents_updated": updated,
                "errors": run.errors,
                "documents": [_serialize_document(row) for row in documents],
                "storage_semantics": {
                    "abstract_text_persisted": False,
                    "metadata_and_source_links_persisted": True,
                    "discovery_signal_is_scientific_validity_probability": False,
                },
            }
        except Exception as exc:
            run.status = "failed"
            run.errors = [{"source": "warehouse", "error": str(exc)[:500]}]
            run.completed_at = _utcnow()
            self.db.commit()
            raise

    def bootstrap(self, payload: BehavioralWarehouseBootstrapRequest) -> dict[str, Any]:
        query_plan: list[tuple[str, str]] = []
        for mechanism in payload.mechanisms:
            for query in MECHANISM_QUERIES.get(mechanism, []):
                query_plan.append(
                    (
                        mechanism,
                        f"{payload.scenario} {payload.population} {query}",
                    )
                )
        query_plan = query_plan[: payload.max_queries]
        runs = []
        total_created = 0
        total_updated = 0
        errors = []
        for mechanism, query in query_plan:
            try:
                result = self.harvest(
                    BehavioralWarehouseHarvestRequest(
                        query=query,
                        sources=["openalex", "pubmed"],
                        limit_per_source=payload.limit_per_source,
                        publication_year_from=payload.publication_year_from,
                        open_access_only=payload.open_access_only,
                    )
                )
                total_created += result["documents_created"]
                total_updated += result["documents_updated"]
                errors.extend(result.get("errors") or [])
                runs.append(
                    {
                        "mechanism": mechanism,
                        "query": query,
                        "run_key": result["run_key"],
                        "documents_seen": result["documents_seen"],
                        "documents_created": result["documents_created"],
                        "documents_updated": result["documents_updated"],
                    }
                )
            except Exception as exc:
                errors.append({"mechanism": mechanism, "query": query, "error": str(exc)[:500]})
        return {
            "engine": self.ENGINE_VERSION,
            "queries_executed": len(query_plan),
            "documents_created": total_created,
            "documents_updated": total_updated,
            "runs": runs,
            "errors": errors,
            "next_gate": "extract_structured_effects_then_review_before_calibration",
        }

    def documents(
        self,
        *,
        source: str | None = None,
        publication_year_from: int | None = None,
        evidence_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = self.db.query(HorizonBehavioralDocument)
        if source:
            query = query.filter(HorizonBehavioralDocument.source == source)
        if publication_year_from:
            query = query.filter(HorizonBehavioralDocument.publication_year >= publication_year_from)
        if evidence_status:
            query = query.filter(HorizonBehavioralDocument.evidence_status == evidence_status)
        total = query.count()
        rows = (
            query.order_by(
                HorizonBehavioralDocument.publication_year.desc(),
                HorizonBehavioralDocument.last_seen_at.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "engine": self.ENGINE_VERSION,
            "total": total,
            "limit": limit,
            "offset": offset,
            "documents": [_serialize_document(row) for row in rows],
        }

    def add_effect(self, payload: BehavioralEffectCreate) -> dict[str, Any]:
        document = (
            self.db.query(HorizonBehavioralDocument)
            .filter_by(document_key=payload.document_key)
            .one_or_none()
        )
        if document is None:
            raise ValueError("behavioral document not found")
        key = _effect_key(payload)
        existing = self.db.query(HorizonBehavioralEffect).filter_by(effect_key=key).one_or_none()
        if existing is not None:
            return {
                "created": False,
                "effect": _serialize_effect(existing, document),
            }
        now = _utcnow()
        row = HorizonBehavioralEffect(
            effect_key=key,
            document_id=document.id,
            mechanism=payload.mechanism,
            construct=payload.construct,
            population=payload.population,
            context=payload.context,
            exposure=payload.exposure,
            behavioral_outcome=payload.behavioral_outcome,
            effect_direction=payload.effect_direction,
            effect_size=payload.effect_size,
            effect_size_type=payload.effect_size_type,
            uncertainty_low=payload.uncertainty_low,
            uncertainty_high=payload.uncertainty_high,
            sample_size=payload.sample_size,
            study_design=payload.study_design,
            replication_status=payload.replication_status,
            preregistered=payload.preregistered,
            peer_reviewed=payload.peer_reviewed,
            countries=list(payload.countries),
            time_horizon=payload.time_horizon,
            evidence_summary=payload.evidence_summary,
            source_locator=payload.source_locator,
            extraction_method=payload.extraction_method,
            extraction_version=payload.extraction_version,
            extraction_confidence=payload.extraction_confidence,
            quality_score=_quality_score(payload),
            evidence_status="candidate",
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        if document.evidence_status == "discovered":
            document.evidence_status = "extracted"
        self.db.commit()
        self.db.refresh(row)
        return {
            "created": True,
            "effect": _serialize_effect(row, document),
        }

    def review_effect(self, effect_key: str, payload: BehavioralEffectReview) -> dict[str, Any]:
        row = self.db.query(HorizonBehavioralEffect).filter_by(effect_key=effect_key).one_or_none()
        if row is None:
            raise ValueError("behavioral effect not found")
        row.evidence_status = payload.status
        row.reviewed_by = payload.reviewed_by
        row.review_notes = payload.notes
        row.reviewed_at = _utcnow()
        row.updated_at = _utcnow()
        document = self.db.query(HorizonBehavioralDocument).filter_by(id=row.document_id).one_or_none()
        if document is not None:
            accepted_count = (
                self.db.query(HorizonBehavioralEffect)
                .filter_by(document_id=document.id, evidence_status="accepted")
                .count()
            )
            if payload.status == "accepted":
                accepted_count += 1 if row.evidence_status == "accepted" else 0
            if payload.status == "accepted" or accepted_count > 0:
                document.evidence_status = "accepted_effect"
            elif payload.status == "rejected":
                document.evidence_status = "reviewed"
            document.updated_at = _utcnow()
        self.db.commit()
        return {
            "effect": _serialize_effect(row, document),
            "eligible_for_calibration_export": row.evidence_status == "accepted",
        }

    def effects(
        self,
        *,
        mechanism: str | None = None,
        evidence_status: str | None = None,
        min_quality_score: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = self.db.query(HorizonBehavioralEffect, HorizonBehavioralDocument).join(
            HorizonBehavioralDocument,
            HorizonBehavioralDocument.id == HorizonBehavioralEffect.document_id,
        )
        if mechanism:
            query = query.filter(HorizonBehavioralEffect.mechanism == mechanism)
        if evidence_status:
            query = query.filter(HorizonBehavioralEffect.evidence_status == evidence_status)
        if min_quality_score is not None:
            query = query.filter(HorizonBehavioralEffect.quality_score >= min_quality_score)
        total = query.count()
        rows = (
            query.order_by(HorizonBehavioralEffect.quality_score.desc(), HorizonBehavioralEffect.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "engine": self.ENGINE_VERSION,
            "total": total,
            "limit": limit,
            "offset": offset,
            "effects": [_serialize_effect(effect, document) for effect, document in rows],
        }

    def calibration_pack(self, payload: BehavioralWarehouseCalibrationPackRequest) -> dict[str, Any]:
        query = (
            self.db.query(HorizonBehavioralEffect, HorizonBehavioralDocument)
            .join(HorizonBehavioralDocument, HorizonBehavioralDocument.id == HorizonBehavioralEffect.document_id)
            .filter(HorizonBehavioralEffect.evidence_status == "accepted")
            .filter(HorizonBehavioralEffect.quality_score >= payload.min_quality_score)
        )
        if payload.mechanisms:
            query = query.filter(HorizonBehavioralEffect.mechanism.in_(payload.mechanisms))
        if payload.publication_year_from:
            query = query.filter(HorizonBehavioralDocument.publication_year >= payload.publication_year_from)
        rows = query.all()
        if payload.countries:
            wanted = {country.upper() for country in payload.countries}
            rows = [
                (effect, document)
                for effect, document in rows
                if not effect.countries
                or wanted.intersection({str(country).upper() for country in effect.countries})
            ]

        grouped: dict[str, list[tuple[HorizonBehavioralEffect, HorizonBehavioralDocument]]] = defaultdict(list)
        for effect, document in rows:
            grouped[effect.mechanism].append((effect, document))

        mechanisms = []
        for mechanism, items in sorted(grouped.items()):
            weight_total = sum(effect.quality_score for effect, _ in items)
            direction_index = (
                sum(effect.quality_score * DIRECTION_VALUE.get(effect.effect_direction, 0.0) for effect, _ in items)
                / weight_total
                if weight_total > 0
                else 0.0
            )
            documents = {document.document_key for _, document in items}
            replicated = sum(effect.replication_status == "replicated" for effect, _ in items)
            randomized = sum(effect.study_design == "randomized_experiment" for effect, _ in items)
            effect_size_types = sorted(
                {
                    effect.effect_size_type
                    for effect, _ in items
                    if effect.effect_size is not None and effect.effect_size_type
                }
            )
            mechanisms.append(
                {
                    "mechanism": mechanism,
                    "accepted_effects": len(items),
                    "independent_documents": len(documents),
                    "mean_quality_score": round(sum(effect.quality_score for effect, _ in items) / len(items), 6),
                    "evidence_direction_index": round(direction_index, 6),
                    "replicated_effects": replicated,
                    "randomized_experiments": randomized,
                    "effect_size_types": effect_size_types,
                    "effect_sizes_directly_poolable": len(effect_size_types) == 1 and len(effect_size_types) > 0,
                    "eligible_for_learning": (
                        len(items) >= payload.min_effects_per_mechanism
                        and len(documents) >= payload.min_effects_per_mechanism
                    ),
                }
            )

        return {
            "engine": self.ENGINE_VERSION,
            "pack_type": "reviewed_behavioral_evidence_for_calibration",
            "filters": payload.model_dump(mode="json"),
            "accepted_effects_considered": len(rows),
            "mechanisms": mechanisms,
            "semantics": {
                "automatically_changes_human_dynamics_coefficients": False,
                "evidence_direction_index_is_effect_size": False,
                "quality_score_is_probability_effect_is_true": False,
                "heterogeneous_effect_sizes_require_metric_specific_modeling": True,
                "pack_is_training_eligible_input_not_trained_model": True,
            },
        }
