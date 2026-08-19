from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_models import (
    HorizonBehaviorPattern,
    HorizonForecast,
    HorizonForecastResolution,
    HorizonGlobalEvent,
    HorizonSocialSignal,
)
from ..horizon_schemas import (
    HorizonEventCreate,
    HorizonForecastRequest,
    HorizonPatternCreate,
    HorizonResolutionCreate,
    HorizonSignalCreate,
)
from ..models import Intent, StateFact, User
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _likelihood_band(score: float) -> str:
    if score >= 0.75:
        return "strong"
    if score >= 0.55:
        return "plausible"
    if score >= 0.35:
        return "emerging"
    return "weak"


class HorizonService:
    ENGINE_VERSION = "horizon-predictive-core-v0.1"

    def __init__(self, db: Session):
        self.db = db

    def create_event(self, payload: HorizonEventCreate) -> HorizonGlobalEvent:
        existing = (
            self.db.query(HorizonGlobalEvent)
            .filter(HorizonGlobalEvent.event_key == payload.event_key)
            .one_or_none()
        )
        if existing:
            raise ValueError("event_key already exists; HORIZON events are immutable snapshots")
        data = payload.model_dump()
        data["occurred_at"] = _utc_naive(data["occurred_at"])
        data["first_observed_at"] = _utc_naive(data["first_observed_at"])
        row = HorizonGlobalEvent(**data)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_signal(self, event_id: int, payload: HorizonSignalCreate) -> HorizonSocialSignal:
        event = self.db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == event_id).one_or_none()
        if not event:
            raise ValueError("HORIZON event not found")
        existing = (
            self.db.query(HorizonSocialSignal)
            .filter(HorizonSocialSignal.signal_key == payload.signal_key)
            .one_or_none()
        )
        if existing:
            raise ValueError("signal_key already exists; social signals are immutable observations")
        data = payload.model_dump()
        data["observed_at"] = _utc_naive(data["observed_at"])
        row = HorizonSocialSignal(event_id=event.id, **data)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def create_pattern(self, payload: HorizonPatternCreate) -> HorizonBehaviorPattern:
        existing = (
            self.db.query(HorizonBehaviorPattern)
            .filter(HorizonBehaviorPattern.pattern_key == payload.pattern_key)
            .one_or_none()
        )
        if existing:
            raise ValueError("pattern_key already exists")
        data = payload.model_dump()
        data["knowledge_available_at"] = _utc_naive(data["knowledge_available_at"])
        row = HorizonBehaviorPattern(**data)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _state_as_of(self, user: User, as_of: datetime) -> dict:
        rows = (
            self.db.query(StateFact)
            .filter(StateFact.user_id == user.id, StateFact.observed_at <= as_of)
            .order_by(StateFact.observed_at.desc(), StateFact.id.desc())
            .all()
        )
        snapshot: dict[str, dict] = {}
        seen: set[tuple[str, str]] = set()
        for row in rows:
            identity = (row.domain, row.key)
            if identity in seen:
                continue
            seen.add(identity)
            if row.expires_at is not None and row.expires_at <= as_of:
                continue
            snapshot[f"{row.domain}.{row.key}"] = {
                "value": row.value,
                "confidence": row.confidence,
                "observed_at": row.observed_at.isoformat(),
            }
        return snapshot

    def _intents_as_of(self, user: User, as_of: datetime) -> list[dict]:
        rows = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.created_at <= as_of, Intent.active == True)  # noqa: E712
            .all()
        )
        return [
            {
                "kind": row.kind,
                "statement": row.statement,
                "target": row.target,
                "priority": row.priority,
            }
            for row in rows
        ]

    def _personal_exposure(self, user: User, event: HorizonGlobalEvent, as_of: datetime) -> dict:
        state = self._state_as_of(user, as_of)
        intents = self._intents_as_of(user, as_of)
        event_geo = {str(item).upper() for item in (event.geography or [])}
        geography_match = not event_geo or "*" in event_geo or user.country.upper() in event_geo

        exposure_keys = [str(item) for item in (event.raw_facts or {}).get("exposure_keys", [])]
        matched_keys = [key for key in exposure_keys if key in state]
        if not exposure_keys:
            state_match_score = 0.5
        else:
            state_match_score = len(matched_keys) / len(exposure_keys)

        intent_keywords = [str(item).lower() for item in (event.raw_facts or {}).get("intent_keywords", [])]
        intent_text = " ".join(item["statement"].lower() for item in intents)
        matched_keywords = [item for item in intent_keywords if item and item in intent_text]
        if not intent_keywords:
            intent_match_score = 0.5
        else:
            intent_match_score = len(matched_keywords) / len(intent_keywords)

        geography_score = 1.0 if geography_match else 0.15
        exposure_score = _clamp(
            0.45 * geography_score + 0.35 * state_match_score + 0.20 * intent_match_score
        )
        return {
            "score": round(exposure_score, 4),
            "country": user.country,
            "geography_match": geography_match,
            "matched_state_keys": matched_keys,
            "matched_intent_keywords": matched_keywords,
            "state_snapshot": state,
            "intent_snapshot": intents,
        }

    @staticmethod
    def _signal_strength(signals: list[HorizonSocialSignal]) -> float:
        if not signals:
            return 0.0
        strengths = []
        for signal in signals:
            magnitude = min(abs(float(signal.normalized_score)) / 3.0, 1.0)
            strengths.append(_clamp(signal.reliability) * magnitude)
        return sum(strengths) / len(strengths)

    @staticmethod
    def _pattern_matches(pattern: HorizonBehaviorPattern, event: HorizonGlobalEvent, signals: list[HorizonSocialSignal]) -> bool:
        allowed_event_types = {str(item) for item in (pattern.event_types or [])}
        if allowed_event_types and "*" not in allowed_event_types and event.event_type not in allowed_event_types:
            return False
        available = {item.signal_type for item in signals}
        required = {str(item) for item in (pattern.required_signal_types or [])}
        return required.issubset(available)

    def forecast_user(self, user: User, request: HorizonForecastRequest) -> list[HorizonForecast]:
        now = datetime.utcnow()
        as_of = _utc_naive(request.as_of) if request.as_of else now
        if request.mode == "live" and as_of > now + timedelta(minutes=5):
            raise ValueError("live forecast as_of cannot be in the future")

        event = (
            self.db.query(HorizonGlobalEvent)
            .filter(HorizonGlobalEvent.id == request.event_id, HorizonGlobalEvent.status == "active")
            .one_or_none()
        )
        if not event:
            raise ValueError("HORIZON event not found")
        if event.first_observed_at > as_of:
            raise ValueError("event was not observable at the requested cutoff")

        signals = (
            self.db.query(HorizonSocialSignal)
            .filter(HorizonSocialSignal.event_id == event.id, HorizonSocialSignal.observed_at <= as_of)
            .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
            .all()
        )
        patterns = (
            self.db.query(HorizonBehaviorPattern)
            .filter(
                HorizonBehaviorPattern.status == "active",
                HorizonBehaviorPattern.knowledge_available_at <= as_of,
            )
            .order_by(HorizonBehaviorPattern.id.asc())
            .all()
        )
        exposure = self._personal_exposure(user, event, as_of)
        source_quality = _clamp(event.source_reliability)
        signal_quality = self._signal_strength(signals)

        created: list[HorizonForecast] = []
        for pattern in patterns:
            if not self._pattern_matches(pattern, event, signals):
                continue
            pattern_quality = _clamp(pattern.confidence)
            predictive_score = _clamp(
                0.20 * source_quality
                + 0.30 * signal_quality
                + 0.25 * pattern_quality
                + 0.25 * float(exposure["score"])
            )
            band = _likelihood_band(predictive_score)
            onset_low = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_low)
            onset_high = event.occurred_at + timedelta(hours=pattern.expected_lag_hours_high)
            if onset_high < as_of:
                window_status = "likely_closed"
                closes_at = as_of
            elif onset_low <= as_of:
                window_status = "closing_or_active"
                closes_at = min(onset_high, as_of + timedelta(hours=24))
            else:
                window_status = "open"
                closes_at = onset_low

            signal_snapshot = [
                {
                    "signal_key": item.signal_key,
                    "signal_type": item.signal_type,
                    "source": item.source,
                    "normalized_score": item.normalized_score,
                    "direction": item.direction,
                    "reliability": item.reliability,
                    "observed_at": item.observed_at.isoformat(),
                    "evidence": item.evidence,
                }
                for item in signals
            ]
            key = sha256_dict(
                {
                    "engine": self.ENGINE_VERSION,
                    "user_id": user.id,
                    "event_id": event.id,
                    "pattern_id": pattern.id,
                    "mode": request.mode,
                    "as_of": as_of.isoformat(),
                }
            )
            existing = (
                self.db.query(HorizonForecast)
                .filter(HorizonForecast.forecast_key == key)
                .one_or_none()
            )
            if existing:
                created.append(existing)
                continue

            row = HorizonForecast(
                forecast_key=key,
                user_id=user.id,
                event_id=event.id,
                pattern_id=pattern.id,
                mode=request.mode,
                as_of=as_of,
                event_facts_snapshot={
                    "event_key": event.event_key,
                    "event_type": event.event_type,
                    "title": event.title,
                    "summary": event.summary,
                    "geography": event.geography,
                    "source": event.source,
                    "source_url": event.source_url,
                    "source_reliability": event.source_reliability,
                    "raw_facts": event.raw_facts,
                    "occurred_at": event.occurred_at.isoformat(),
                    "first_observed_at": event.first_observed_at.isoformat(),
                },
                social_signal_snapshot=signal_snapshot,
                personal_exposure=exposure,
                behavior_chain=pattern.mechanism_chain,
                predicted_outcome=pattern.predicted_response,
                likelihood_band=band,
                predictive_score=round(predictive_score, 4),
                probability_low=None,
                probability_mid=None,
                probability_high=None,
                probability_basis="not_calibrated",
                expected_onset_low=onset_low,
                expected_onset_high=onset_high,
                decision_window={
                    "status": window_status,
                    "opens_at": as_of.isoformat(),
                    "closes_at": closes_at.isoformat(),
                    "basis": "behavior_pattern_expected_lag",
                    "action_prescribed": False,
                },
                reasons=[
                    {"component": "source_quality", "score": round(source_quality, 4)},
                    {"component": "social_signal_strength", "score": round(signal_quality, 4)},
                    {"component": "behavior_pattern_confidence", "score": round(pattern_quality, 4)},
                    {"component": "personal_exposure", "score": round(float(exposure["score"]), 4)},
                ],
            )
            self.db.add(row)
            self.db.flush()
            created.append(row)

        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def resolve_forecast(self, forecast: HorizonForecast, payload: HorizonResolutionCreate) -> HorizonForecastResolution:
        obvious_at = _utc_naive(payload.became_obvious_at) if payload.became_obvious_at else None
        action_at = _utc_naive(payload.personal_action_at) if payload.personal_action_at else None
        if obvious_at is not None and obvious_at < forecast.as_of:
            raise ValueError("became_obvious_at cannot predate the forecast cutoff")
        if action_at is not None and action_at < forecast.as_of:
            raise ValueError("personal_action_at cannot predate the forecast cutoff")
        if obvious_at is not None and action_at is not None and action_at > obvious_at:
            raise ValueError("personal_action_at cannot be after became_obvious_at")

        lead = None
        actionable = None
        if obvious_at is not None:
            lead = round((obvious_at - forecast.as_of).total_seconds() / 3600.0, 3)
            if action_at is not None:
                actionable = round((obvious_at - action_at).total_seconds() / 3600.0, 3)

        row = (
            self.db.query(HorizonForecastResolution)
            .filter(HorizonForecastResolution.forecast_id == forecast.id)
            .one_or_none()
        )
        data = payload.model_dump()
        data["became_obvious_at"] = obvious_at
        data["personal_action_at"] = action_at
        data["predictive_lead_time_hours"] = lead
        data["actionable_lead_time_hours"] = actionable
        if row is None:
            row = HorizonForecastResolution(forecast_id=forecast.id, **data)
            self.db.add(row)
        else:
            for key, value in data.items():
                setattr(row, key, value)
            row.resolved_at = datetime.utcnow()

        forecast.status = "resolved"
        forecast.calibration_status = "labeled"
        self.db.commit()
        self.db.refresh(row)
        return row

    def calibration_summary(self, user: User) -> dict:
        forecasts = self.db.query(HorizonForecast).filter(HorizonForecast.user_id == user.id).all()
        ids = [item.id for item in forecasts]
        resolutions = []
        if ids:
            resolutions = (
                self.db.query(HorizonForecastResolution)
                .filter(HorizonForecastResolution.forecast_id.in_(ids))
                .all()
            )
        decisive = [item for item in resolutions if item.correctness in {"confirmed", "partial", "false"}]
        correct_weight = sum(1.0 if item.correctness == "confirmed" else 0.5 if item.correctness == "partial" else 0.0 for item in decisive)
        lead_times = [
            float(item.predictive_lead_time_hours)
            for item in resolutions
            if item.predictive_lead_time_hours is not None and item.correctness in {"confirmed", "partial"}
        ]
        return {
            "forecasts": len(forecasts),
            "resolved": len(resolutions),
            "decisive_labels": len(decisive),
            "weighted_precision": round(correct_weight / len(decisive), 4) if decisive else None,
            "mean_predictive_lead_time_hours": round(sum(lead_times) / len(lead_times), 3) if lead_times else None,
            "probability_calibration_enabled": False,
            "reason": "numeric probabilities remain disabled until enough labeled backtests exist",
        }
