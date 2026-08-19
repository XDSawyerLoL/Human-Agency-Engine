from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern, HorizonGlobalEvent
from ..horizon_provisional_models import HorizonProvisionalForecast, HorizonProvisionalResolution
from ..horizon_provisional_schemas import HorizonProvisionalReconcileRequest, HorizonProvisionalRefreshRequest
from ..horizon_source_models import HorizonEventCandidate
from .horizon_response_library import HorizonResponseLibraryService
from .policy import sha256_dict


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _band(score: float) -> str:
    if score >= 0.70:
        return "elevated_watch"
    if score >= 0.45:
        return "watch"
    return "weak_watch"


class HorizonProvisionalService:
    ENGINE_VERSION = "horizon-provisional-forecast-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _pattern_applies(pattern: HorizonBehaviorPattern, candidate: HorizonEventCandidate) -> bool:
        allowed = {str(item) for item in (pattern.event_types or [])}
        return not allowed or "*" in allowed or candidate.event_type in allowed

    def refresh(self, request: HorizonProvisionalRefreshRequest) -> dict:
        now = datetime.utcnow()
        HorizonResponseLibraryService(self.db).sync_builtins()
        candidates = (
            self.db.query(HorizonEventCandidate)
            .filter(
                HorizonEventCandidate.promotion_status == "candidate",
                HorizonEventCandidate.promoted_event_id.is_(None),
            )
            .order_by(HorizonEventCandidate.first_observed_at.asc(), HorizonEventCandidate.id.asc())
            .limit(request.max_candidates)
            .all()
        )
        patterns = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= now,
            )
            .order_by(HorizonBehaviorPattern.id.asc())
            .all()
        )

        created = 0
        reused = 0
        skipped = 0
        forecasts: list[dict] = []
        for candidate in candidates:
            applicable = [item for item in patterns if self._pattern_applies(item, candidate)]
            if not applicable:
                skipped += 1
                continue
            for pattern in applicable:
                key = sha256_dict(
                    {
                        "engine": self.ENGINE_VERSION,
                        "candidate_key": candidate.candidate_key,
                        "pattern_key": pattern.pattern_key,
                    }
                )
                existing = (
                    self.db.query(HorizonProvisionalForecast)
                    .filter(HorizonProvisionalForecast.forecast_key == key)
                    .one_or_none()
                )
                if existing is not None:
                    reused += 1
                    row = existing
                else:
                    class_count = len({str(item) for item in (candidate.source_classes or [])})
                    source_class_diversity = _clamp(class_count / 2.0)
                    provisional_score = _clamp(
                        0.45 * _clamp(candidate.corroboration_score)
                        + 0.35 * _clamp(pattern.confidence)
                        + 0.20 * source_class_diversity
                    )
                    normalized = candidate.normalized_facts or {}
                    geography_status = str(normalized.get("geography_status") or (
                        "known" if candidate.geography else "unknown"
                    ))
                    row = HorizonProvisionalForecast(
                        forecast_key=key,
                        candidate_id=candidate.id,
                        pattern_id=pattern.id,
                        as_of=now,
                        fact_status="unconfirmed_emerging_event",
                        candidate_snapshot={
                            "candidate_key": candidate.candidate_key,
                            "event_type": candidate.event_type,
                            "title": candidate.title,
                            "geography": candidate.geography,
                            "source_classes": candidate.source_classes,
                            "normalized_facts": candidate.normalized_facts,
                            "corroboration_score": candidate.corroboration_score,
                            "first_observed_at": candidate.first_observed_at.isoformat(),
                            "last_observed_at": candidate.last_observed_at.isoformat(),
                            "promotion_status": candidate.promotion_status,
                        },
                        pattern_snapshot={
                            "pattern_key": pattern.pattern_key,
                            "name": pattern.name,
                            "predicted_response": pattern.predicted_response,
                            "mechanism_chain": pattern.mechanism_chain,
                            "expected_lag_hours_low": pattern.expected_lag_hours_low,
                            "expected_lag_hours_high": pattern.expected_lag_hours_high,
                            "confidence": pattern.confidence,
                            "provenance": pattern.provenance,
                        },
                        source_classes=candidate.source_classes or [],
                        corroboration_score=float(candidate.corroboration_score),
                        provisional_score=round(provisional_score, 4),
                        hypothesis_band=_band(provisional_score),
                        predicted_response=pattern.predicted_response,
                        probability_basis="not_calibrated",
                        geography_status=geography_status,
                        user_surface_allowed=False,
                        external_action_allowed=False,
                        interpretation={
                            "fact_status": "unconfirmed_emerging_event",
                            "candidate_is_confirmed_fact": False,
                            "provisional_score_is_probability": False,
                            "formal_probability_enabled": False,
                            "user_notification_allowed": False,
                            "external_action_allowed": False,
                            "absolute_onset_window_available": False,
                            "reason_absolute_onset_unavailable": (
                                "an unconfirmed candidate has no verified event-occurrence anchor; "
                                "pattern lag is preserved but not converted into fake dates"
                            ),
                            "relative_lag_hours": {
                                "low": pattern.expected_lag_hours_low,
                                "high": pattern.expected_lag_hours_high,
                            },
                        },
                    )
                    self.db.add(row)
                    self.db.commit()
                    self.db.refresh(row)
                    created += 1
                forecasts.append(
                    {
                        "forecast_id": row.id,
                        "candidate_id": row.candidate_id,
                        "pattern_id": row.pattern_id,
                        "fact_status": row.fact_status,
                        "hypothesis_band": row.hypothesis_band,
                        "provisional_score": row.provisional_score,
                        "probability_basis": row.probability_basis,
                        "geography_status": row.geography_status,
                        "user_surface_allowed": row.user_surface_allowed,
                    }
                )

        return {
            "candidates_scanned": len(candidates),
            "forecasts_created": created,
            "forecasts_reused": reused,
            "candidates_without_pattern": skipped,
            "forecasts": forecasts,
            "provisional_forecasts_are_confirmed_facts": False,
            "user_notification_performed": False,
            "external_action_executed": False,
        }

    def reconcile(self, request: HorizonProvisionalReconcileRequest) -> dict:
        forecasts = (
            self.db.query(HorizonProvisionalForecast)
            .outerjoin(
                HorizonProvisionalResolution,
                HorizonProvisionalResolution.forecast_id == HorizonProvisionalForecast.id,
            )
            .filter(HorizonProvisionalResolution.id.is_(None))
            .order_by(HorizonProvisionalForecast.as_of.asc(), HorizonProvisionalForecast.id.asc())
            .limit(request.max_forecasts)
            .all()
        )
        resolved = 0
        waiting = 0
        rows: list[dict] = []
        for forecast in forecasts:
            candidate = self.db.query(HorizonEventCandidate).filter(
                HorizonEventCandidate.id == forecast.candidate_id
            ).one_or_none()
            if candidate is None or candidate.promoted_event_id is None:
                waiting += 1
                continue
            event = self.db.query(HorizonGlobalEvent).filter(
                HorizonGlobalEvent.id == candidate.promoted_event_id
            ).one_or_none()
            if event is None:
                waiting += 1
                continue
            corroborated_at = event.created_at
            lead = max(0.0, (corroborated_at - forecast.as_of).total_seconds() / 3600.0)
            resolution = HorizonProvisionalResolution(
                forecast_id=forecast.id,
                resolution_type="corroborated_into_confirmed_event",
                promoted_event_id=event.id,
                corroborated_at=corroborated_at,
                corroboration_lead_time_hours=round(lead, 3),
                predictive_lead_time_hours=None,
                evidence={
                    "candidate_key": candidate.candidate_key,
                    "promoted_event_key": event.event_key,
                    "promotion_status": candidate.promotion_status,
                    "corroboration_lead_time_is_predictive_lead_time": False,
                    "predictive_lead_requires_later_materialization_label": True,
                },
            )
            self.db.add(resolution)
            self.db.commit()
            self.db.refresh(resolution)
            resolved += 1
            rows.append(
                {
                    "resolution_id": resolution.id,
                    "forecast_id": forecast.id,
                    "promoted_event_id": event.id,
                    "corroboration_lead_time_hours": resolution.corroboration_lead_time_hours,
                    "predictive_lead_time_hours": None,
                }
            )
        return {
            "forecasts_scanned": len(forecasts),
            "resolved_by_corroboration": resolved,
            "still_unconfirmed": waiting,
            "resolutions": rows,
            "corroboration_lead_time_is_predictive_lead_time": False,
        }
