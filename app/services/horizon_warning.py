from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_cascade_schemas import HorizonCascadeRequest
from ..horizon_models import HorizonBehaviorPattern, HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_warning_models import HorizonEarlyWarningEpisode, HorizonEarlyWarningSnapshot
from ..horizon_warning_schemas import HorizonWarningProjectRequest, HorizonWarningRefreshRequest
from .horizon_cascade import HorizonCascadeService
from .policy import sha256_dict


SIGNAL_FAMILIES = {
    "media_attention": "attention",
    "search_interest": "search_behavior",
    "search_demand": "search_behavior",
    "purchase_activity": "purchase_behavior",
    "purchase_demand": "purchase_behavior",
    "stock_availability": "material_availability",
    "price_pressure": "market_price",
    "queue_activity": "physical_behavior",
    "mobility": "mobility",
    "official_warning": "official_state",
}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class HorizonWarningService:
    ENGINE_VERSION = "horizon-early-warning-v0.1"
    PASSIVE_TIME_BUCKET_SECONDS = 6 * 60 * 60

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _pattern_applies(pattern: HorizonBehaviorPattern, event: HorizonGlobalEvent) -> bool:
        allowed = {str(item) for item in (pattern.event_types or [])}
        return not allowed or "*" in allowed or event.event_type in allowed

    @staticmethod
    def _family(signal: HorizonSocialSignal) -> str:
        # Unknown signal types intentionally collapse into one family. This avoids
        # inflating convergence by inventing many labels for effectively the same
        # weak evidence class.
        return SIGNAL_FAMILIES.get(str(signal.signal_type), "other")

    @staticmethod
    def _band(family_count: int, source_count: int, score: float, cascade_stage: str) -> str:
        if (
            family_count >= 3
            and source_count >= 3
            and score >= 0.65
            and cascade_stage not in {"", "pre-cascade / latent"}
        ):
            return "strong_convergence"
        if family_count >= 2 and source_count >= 2:
            return "converging"
        return "emerging"

    def project(self, request: HorizonWarningProjectRequest) -> HorizonEarlyWarningSnapshot:
        now = datetime.utcnow()
        as_of = _utc_naive(request.as_of) if request.as_of else now
        if request.mode == "live" and as_of > now + timedelta(minutes=5):
            raise ValueError("live early-warning as_of cannot be in the future")

        event = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.id == request.event_id,
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at <= as_of,
            )
            .one_or_none()
        )
        if event is None:
            raise ValueError("HORIZON event not observable at requested cutoff")

        pattern = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.id == request.pattern_id,
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= as_of,
            )
            .one_or_none()
        )
        if pattern is None or not self._pattern_applies(pattern, event):
            raise ValueError("behavior pattern does not apply or was unavailable at cutoff")

        recency_cutoff = as_of - timedelta(hours=request.recency_hours)
        signals = (
            self.db.query(HorizonSocialSignal)
            .filter(
                HorizonSocialSignal.event_id == event.id,
                HorizonSocialSignal.observed_at <= as_of,
                HorizonSocialSignal.observed_at >= recency_cutoff,
            )
            .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
            .all()
        )
        if not signals:
            raise ValueError("no recent social/material signals for early-warning episode")

        cascade = HorizonCascadeService(self.db).project(
            HorizonCascadeRequest(
                event_id=event.id,
                pattern_id=pattern.id,
                as_of=as_of,
                mode=request.mode,
            )
        )

        families = sorted({self._family(item) for item in signals})
        sources = sorted({str(item.source) for item in signals})
        family_count = len(families)
        source_count = len(sources)

        family_diversity = _clamp(family_count / 3.0)
        source_diversity = _clamp(source_count / 3.0)
        avg_reliability = sum(_clamp(item.reliability) for item in signals) / len(signals)
        avg_strength = sum(_clamp(abs(float(item.normalized_score))) for item in signals) / len(signals)
        freshness = sum(
            _clamp(
                1.0
                - max(0.0, (as_of - item.observed_at).total_seconds() / 3600.0)
                / float(request.recency_hours)
            )
            for item in signals
        ) / len(signals)
        convergence_score = _clamp(
            0.30 * family_diversity
            + 0.20 * source_diversity
            + 0.20 * avg_reliability
            + 0.15 * freshness
            + 0.10 * avg_strength
            + 0.05 * _clamp(cascade.propagation_score)
        )
        band = self._band(family_count, source_count, convergence_score, cascade.current_stage)

        onset_low = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_low)
        onset_high = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_high)
        lead_low = max(0.0, (onset_low - as_of).total_seconds() / 3600.0)
        lead_high = max(0.0, (onset_high - as_of).total_seconds() / 3600.0)
        if onset_high < as_of:
            lead_status = "pattern_window_elapsed"
        elif onset_low <= as_of <= onset_high:
            lead_status = "inside_expected_transition_window"
        else:
            lead_status = "before_expected_transition_window"

        episode_key = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "event_id": event.id,
                "pattern_id": pattern.id,
                "mode": request.mode,
            }
        )
        episode = (
            self.db.query(HorizonEarlyWarningEpisode)
            .filter(HorizonEarlyWarningEpisode.episode_key == episode_key)
            .one_or_none()
        )
        if episode is None:
            episode = HorizonEarlyWarningEpisode(
                episode_key=episode_key,
                event_id=event.id,
                pattern_id=pattern.id,
                mode=request.mode,
                opened_at=min(item.observed_at for item in signals),
                current_band=band,
                current_score=round(convergence_score, 4),
                status="open",
            )
            self.db.add(episode)
            self.db.commit()
            self.db.refresh(episode)

        time_component = (
            as_of.isoformat()
            if request.mode == "backtest"
            else int(as_of.timestamp()) // self.PASSIVE_TIME_BUCKET_SECONDS
        )
        input_hash = sha256_dict(
            {
                "event_key": event.event_key,
                "pattern_key": pattern.pattern_key,
                "time_component": time_component,
                "signals": [
                    {
                        "signal_key": item.signal_key,
                        "type": item.signal_type,
                        "family": self._family(item),
                        "source": item.source,
                        "score": item.normalized_score,
                        "reliability": item.reliability,
                        "observed_at": item.observed_at.isoformat(),
                    }
                    for item in signals
                ],
                "cascade_key": cascade.cascade_key,
            }
        )
        snapshot_key = sha256_dict(
            {"engine": self.ENGINE_VERSION, "episode_id": episode.id, "input_hash": input_hash}
        )
        existing = (
            self.db.query(HorizonEarlyWarningSnapshot)
            .filter(HorizonEarlyWarningSnapshot.snapshot_key == snapshot_key)
            .one_or_none()
        )
        if existing is not None:
            return existing

        evidence = [
            {
                "signal_key": item.signal_key,
                "signal_type": item.signal_type,
                "signal_family": self._family(item),
                "source": item.source,
                "direction": item.direction,
                "normalized_score": item.normalized_score,
                "reliability": item.reliability,
                "observed_at": item.observed_at.isoformat(),
            }
            for item in signals
        ]
        snapshot = HorizonEarlyWarningSnapshot(
            snapshot_key=snapshot_key,
            episode_id=episode.id,
            as_of=as_of,
            input_hash=input_hash,
            signal_families=families,
            family_count=family_count,
            source_count=source_count,
            convergence_score=round(convergence_score, 4),
            convergence_band=band,
            cascade_stage=cascade.current_stage,
            expected_onset_low=onset_low,
            expected_onset_high=onset_high,
            remaining_lead_low_hours=round(lead_low, 2),
            remaining_lead_high_hours=round(lead_high, 2),
            evidence_snapshot=evidence,
            interpretation={
                "convergence_score_is_probability": False,
                "formal_probability_enabled": False,
                "probability_basis": "not_calibrated",
                "independent_signal_family_count": family_count,
                "distinct_source_count": source_count,
                "lead_hours_are_measured_predictive_lead_time": False,
                "lead_window_status": lead_status,
                "human_readable": (
                    f"HORIZON sees '{band}' across {family_count} signal families "
                    f"and {source_count} distinct sources. Current sequential behavior stage: "
                    f"'{cascade.current_stage}'."
                ),
            },
        )
        self.db.add(snapshot)
        episode.current_band = band
        episode.current_score = round(convergence_score, 4)
        episode.updated_at = now
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def refresh(self, request: HorizonWarningRefreshRequest) -> dict:
        now = datetime.utcnow()
        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at <= now,
            )
            .order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
            .limit(request.max_events)
            .all()
        )
        patterns = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= now,
            )
            .all()
        )
        totals = {
            "events_scanned": len(events),
            "pairs_projected": 0,
            "episodes": 0,
            "emerging": 0,
            "converging": 0,
            "strong_convergence": 0,
            "skipped_no_signal": 0,
            "errors": [],
            "score_is_probability": False,
        }
        seen_episode_ids: set[int] = set()
        for event in events:
            for pattern in patterns:
                if not self._pattern_applies(pattern, event):
                    continue
                try:
                    snapshot = self.project(
                        HorizonWarningProjectRequest(
                            event_id=event.id,
                            pattern_id=pattern.id,
                            mode="live",
                            recency_hours=request.recency_hours,
                        )
                    )
                except ValueError as exc:
                    if "no recent" in str(exc):
                        totals["skipped_no_signal"] += 1
                        continue
                    if len(totals["errors"]) < 25:
                        totals["errors"].append(
                            {"event_id": event.id, "pattern_id": pattern.id, "error": str(exc)[:250]}
                        )
                    continue
                totals["pairs_projected"] += 1
                totals[snapshot.convergence_band] += 1
                if snapshot.episode_id not in seen_episode_ids:
                    seen_episode_ids.add(snapshot.episode_id)
                    totals["episodes"] += 1
        totals["errors_count"] = len(totals["errors"])
        return totals
