from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..horizon_models import HorizonGlobalEvent
from ..horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .policy import sha256_dict


BUILTIN_SOURCES = (
    HorizonSourceUpsert(
        source_key="gdelt-doc-2",
        name="GDELT DOC 2.0",
        source_class="news_global",
        adapter_kind="gdelt_doc_json",
        domains=["world_events", "news_attention"],
        geography=["*"],
        base_locator="https://api.gdeltproject.org/api/v2/doc/doc",
        trust_weight=0.55,
        refresh_seconds=900,
        requires_credentials=False,
        metadata_json={
            "role": "broad_detection_not_ground_truth",
            "supports_json": True,
            "minimum_timespan_minutes": 15,
        },
    ),
    HorizonSourceUpsert(
        source_key="meteofrance-vigilance",
        name="Meteo-France Vigilance",
        source_class="official_primary",
        adapter_kind="meteofrance_vigilance_json",
        domains=["weather", "civil_protection"],
        geography=["FR"],
        base_locator="https://portail-api.meteofrance.fr/web/fr/api/DonneesPubliquesVigilance",
        trust_weight=0.97,
        refresh_seconds=600,
        requires_credentials=True,
        metadata_json={
            "role": "official_weather_warning",
            "credential_policy": "server_secret_only",
            "rate_limit_per_minute": 60,
        },
    ),
)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _candidate_score(sources: list[HorizonSource]) -> float:
    if not sources:
        return 0.0
    distinct_classes = len({item.source_class for item in sources})
    distinct_sources = len({item.id for item in sources})
    strongest = max(float(item.trust_weight) for item in sources)
    mean = sum(float(item.trust_weight) for item in sources) / len(sources)
    diversity = min(distinct_sources / 3.0, 1.0)
    class_diversity = min(distinct_classes / 3.0, 1.0)
    return round(min(1.0, 0.35 * strongest + 0.25 * mean + 0.20 * diversity + 0.20 * class_diversity), 4)


def _observation_payload(source: HorizonSource, payload: HorizonObservationIngest) -> tuple[dict, str]:
    data = payload.model_dump()
    data["event_time"] = _utc_naive(data["event_time"])
    data["published_at"] = _utc_naive(data["published_at"])
    data["observed_at"] = _utc_naive(data["observed_at"])
    payload_hash = sha256_dict({
        "source_key": source.source_key,
        "external_key": payload.external_key,
        "observation_type": payload.observation_type,
        "title": payload.title,
        "summary": payload.summary,
        "source_url": payload.source_url,
        "geography": payload.geography,
        "canonical_facts": payload.canonical_facts,
        "raw_metadata": payload.raw_metadata,
        "event_time": data["event_time"].isoformat() if data["event_time"] else None,
        "published_at": data["published_at"].isoformat() if data["published_at"] else None,
        "observed_at": data["observed_at"].isoformat(),
    })
    return data, payload_hash


class HorizonSourceService:
    def __init__(self, db: Session):
        self.db = db

    def sync_builtin_sources(self) -> list[HorizonSource]:
        rows = []
        for payload in BUILTIN_SOURCES:
            row = self.db.query(HorizonSource).filter(HorizonSource.source_key == payload.source_key).one_or_none()
            data = payload.model_dump()
            if row is None:
                row = HorizonSource(**data)
                self.db.add(row)
            else:
                enabled = row.enabled
                for key, value in data.items():
                    if key != "enabled":
                        setattr(row, key, value)
                row.enabled = enabled
                row.updated_at = datetime.utcnow()
            rows.append(row)
        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def upsert_source(self, payload: HorizonSourceUpsert) -> HorizonSource:
        row = self.db.query(HorizonSource).filter(HorizonSource.source_key == payload.source_key).one_or_none()
        data = payload.model_dump()
        if row is None:
            row = HorizonSource(**data)
            self.db.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def ingest_observation(self, source: HorizonSource, payload: HorizonObservationIngest) -> tuple[HorizonRawObservation, bool]:
        data, payload_hash = _observation_payload(source, payload)
        existing = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.external_key == payload.external_key,
        ).one_or_none()
        if existing:
            if existing.payload_hash != payload_hash:
                raise ValueError("observation external_key collision with different immutable payload")
            return existing, False
        row = HorizonRawObservation(source_id=source.id, payload_hash=payload_hash, **data)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row, True

    def build_candidate(self, payload: HorizonCandidateBuild) -> HorizonEventCandidate:
        observations = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.id.in_(payload.observation_ids)
        ).all()
        if len({item.id for item in observations}) != len(set(payload.observation_ids)):
            raise ValueError("one or more observations do not exist")
        sources = self.db.query(HorizonSource).filter(
            HorizonSource.id.in_({item.source_id for item in observations})
        ).all()
        first = min(item.observed_at for item in observations)
        last = max(item.observed_at for item in observations)
        observation_hashes = sorted(item.payload_hash for item in observations)
        candidate_key = sha256_dict({
            "event_type": payload.event_type,
            "title": payload.title.strip().lower(),
            "geography": sorted(str(item).upper() for item in payload.geography),
            "observation_hashes": observation_hashes,
            "normalized_facts": payload.normalized_facts,
            "normalizer_version": payload.normalizer_version,
        })
        existing = self.db.query(HorizonEventCandidate).filter(
            HorizonEventCandidate.candidate_key == candidate_key
        ).one_or_none()
        if existing:
            return existing
        row = HorizonEventCandidate(
            candidate_key=candidate_key,
            event_type=payload.event_type,
            title=payload.title,
            geography=payload.geography,
            corroborating_observation_ids=sorted(item.id for item in observations),
            source_classes=sorted({item.source_class for item in sources}),
            normalized_facts=payload.normalized_facts,
            normalizer_version=payload.normalizer_version,
            corroboration_score=_candidate_score(sources),
            promotion_status="candidate",
            first_observed_at=first,
            last_observed_at=last,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def promotion_readiness(self, candidate: HorizonEventCandidate) -> dict:
        ids = [int(item) for item in candidate.corroborating_observation_ids]
        observations = self.db.query(HorizonRawObservation).filter(HorizonRawObservation.id.in_(ids)).all()
        sources = self.db.query(HorizonSource).filter(
            HorizonSource.id.in_({item.source_id for item in observations})
        ).all() if observations else []
        official_primary = [item for item in sources if item.source_class == "official_primary"]
        distinct_sources = len({item.id for item in sources})
        distinct_classes = len({item.source_class for item in sources})
        ready = bool(official_primary) or (
            distinct_sources >= 2
            and distinct_classes >= 2
            and float(candidate.corroboration_score) >= 0.55
        )
        return {
            "ready": ready,
            "official_primary_present": bool(official_primary),
            "distinct_sources": distinct_sources,
            "distinct_source_classes": distinct_classes,
            "corroboration_score": candidate.corroboration_score,
            "corroboration_score_is_probability": False,
            "rule": "official_primary OR >=2 sources across >=2 classes with diagnostic score >=0.55",
        }

    def promote_candidate(self, candidate: HorizonEventCandidate) -> HorizonGlobalEvent:
        if candidate.promoted_event_id is not None:
            return self.db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == candidate.promoted_event_id).one()
        readiness = self.promotion_readiness(candidate)
        if not readiness["ready"]:
            raise ValueError("candidate is not sufficiently corroborated for promotion")
        ids = [int(item) for item in candidate.corroborating_observation_ids]
        observations = self.db.query(HorizonRawObservation).filter(HorizonRawObservation.id.in_(ids)).all()
        sources_by_id = {
            item.id: item for item in self.db.query(HorizonSource).filter(
                HorizonSource.id.in_({obs.source_id for obs in observations})
            ).all()
        }
        ranked = sorted(
            observations,
            key=lambda obs: (
                float(sources_by_id[obs.source_id].trust_weight),
                obs.published_at or obs.event_time or obs.observed_at,
            ),
            reverse=True,
        )
        primary = ranked[0]
        primary_source = sources_by_id[primary.source_id]
        event_key = f"src-{candidate.candidate_key[:32]}"
        raw_facts = {
            "canonical_facts": primary.canonical_facts,
            "normalized_facts": candidate.normalized_facts,
            "normalizer_version": candidate.normalizer_version,
            "corroboration": readiness,
            "observation_ids": sorted(ids),
            "source_keys": sorted({sources_by_id[item.source_id].source_key for item in observations}),
            "source_classes": candidate.source_classes,
        }
        personal_scope = (candidate.normalized_facts or {}).get("personal_scope")
        if isinstance(personal_scope, dict) and personal_scope:
            raw_facts["personal_scope"] = personal_scope
        row = HorizonGlobalEvent(
            event_key=event_key,
            event_type=candidate.event_type,
            title=candidate.title,
            summary=primary.summary,
            geography=candidate.geography,
            source=primary_source.source_key,
            source_url=primary.source_url,
            source_reliability=primary_source.trust_weight,
            raw_facts=raw_facts,
            occurred_at=primary.event_time or primary.published_at or primary.observed_at,
            first_observed_at=candidate.first_observed_at,
            status="active",
        )
        self.db.add(row)
        self.db.flush()
        candidate.promoted_event_id = row.id
        candidate.promotion_status = "promoted"
        self.db.commit()
        self.db.refresh(row)
        return row
