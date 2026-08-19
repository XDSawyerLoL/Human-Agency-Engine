from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..horizon_emerging_schemas import HorizonEmergingClusterRequest
from ..horizon_source_models import HorizonEventCandidate, HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild
from .horizon_sources import HorizonSourceService


NORMALIZER_VERSION = "gdelt-emerging-cluster-v0.1"

SUPPLY_TERMS = (
    "shortage",
    "shortages",
    "rationing",
    "supply disruption",
    "fuel shortage",
    "blockade",
    "pénurie",
    "penurie",
)
HEAT_TERMS = (
    "heatwave",
    "heat wave",
    "extreme heat",
    "canicule",
    "vague de chaleur",
)


def _bucket_start(value: datetime, minutes: int) -> datetime:
    minute = (value.minute // minutes) * minutes
    return value.replace(minute=minute, second=0, microsecond=0)


def _classify(observation: HorizonRawObservation) -> str | None:
    facts = observation.canonical_facts or {}
    family = str(facts.get("watch_family") or "")
    text = f"{observation.title} {observation.summary}".lower()
    if family == "supply" and any(term in text for term in SUPPLY_TERMS):
        return "supply_disruption"
    if family == "weather_disaster" and any(term in text for term in HEAT_TERMS):
        return "extreme_heat"
    return None


class HorizonEmergingService:
    """Build unconfirmed event hypotheses from closed GDELT observation buckets.

    Candidates are deliberately not promoted here. Multiple reports from GDELT
    still represent one `news_global` source class and therefore cannot become
    confirmed facts by repetition alone.
    """

    def __init__(self, db: Session):
        self.db = db

    def cluster_gdelt(
        self,
        request: HorizonEmergingClusterRequest,
        *,
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.utcnow()
        current_bucket = _bucket_start(now, request.bucket_minutes)
        earliest = current_bucket - timedelta(
            minutes=request.bucket_minutes * request.lookback_buckets
        )
        source = (
            self.db.query(HorizonSource)
            .filter(HorizonSource.source_key == "gdelt-doc-2")
            .one_or_none()
        )
        if source is None:
            HorizonSourceService(self.db).sync_builtin_sources()
            source = (
                self.db.query(HorizonSource)
                .filter(HorizonSource.source_key == "gdelt-doc-2")
                .one()
            )

        rows = (
            self.db.query(HorizonRawObservation)
            .filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.observation_type == "news_report",
                HorizonRawObservation.observed_at >= earliest,
                HorizonRawObservation.observed_at < current_bucket,
            )
            .order_by(HorizonRawObservation.observed_at.asc(), HorizonRawObservation.id.asc())
            .all()
        )

        grouped: dict[tuple[datetime, str], list[HorizonRawObservation]] = defaultdict(list)
        ignored_unclassified = 0
        for row in rows:
            event_type = _classify(row)
            if event_type is None:
                ignored_unclassified += 1
                continue
            grouped[(_bucket_start(row.observed_at, request.bucket_minutes), event_type)].append(row)

        results: list[dict] = []
        below_threshold = 0
        source_service = HorizonSourceService(self.db)
        for (bucket, event_type), observations in sorted(grouped.items(), key=lambda item: item[0]):
            if len(observations) < request.min_articles:
                below_threshold += 1
                continue
            selected = observations[:100]
            bucket_end = bucket + timedelta(minutes=request.bucket_minutes)
            family = str((selected[0].canonical_facts or {}).get("watch_family") or "")
            title = (
                "Emerging supply-disruption report cluster"
                if event_type == "supply_disruption"
                else "Emerging extreme-heat report cluster"
            )
            candidate = source_service.build_candidate(
                HorizonCandidateBuild(
                    observation_ids=[item.id for item in selected],
                    event_type=event_type,
                    title=title,
                    geography=[],
                    normalized_facts={
                        "fact_status": "unconfirmed_emerging_event",
                        "candidate_not_fact": True,
                        "raw_claims_verified": False,
                        "detection_basis": "multiple_news_reports_single_global_radar",
                        "watch_family": family,
                        "article_count": len(selected),
                        "bucket_start": bucket.isoformat(),
                        "bucket_end": bucket_end.isoformat(),
                        "geography_status": "unknown",
                        "source_key": source.source_key,
                        "source_class": source.source_class,
                    },
                    normalizer_version=NORMALIZER_VERSION,
                )
            )
            readiness = source_service.promotion_readiness(candidate)
            results.append(
                {
                    "candidate_id": candidate.id,
                    "candidate_key": candidate.candidate_key,
                    "event_type": candidate.event_type,
                    "title": candidate.title,
                    "first_observed_at": candidate.first_observed_at,
                    "last_observed_at": candidate.last_observed_at,
                    "article_count": len(selected),
                    "fact_status": "unconfirmed_emerging_event",
                    "promotion_ready": readiness["ready"],
                    "promotion_rule": readiness["rule"],
                    "corroboration_score": candidate.corroboration_score,
                    "corroboration_score_is_probability": False,
                }
            )

        return {
            "source_key": source.source_key,
            "closed_bucket_end": current_bucket,
            "lookback_start": earliest,
            "raw_observations_scanned": len(rows),
            "ignored_unclassified": ignored_unclassified,
            "groups_below_threshold": below_threshold,
            "candidates": results,
            "candidate_count": len(results),
            "candidates_are_confirmed_facts": False,
            "automatic_promotion_performed": False,
        }
