from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_cascade_models import HorizonBehaviorCascade
from ..horizon_cascade_schemas import HorizonCascadeRequest
from ..horizon_models import HorizonBehaviorPattern, HorizonGlobalEvent, HorizonSocialSignal
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _band(score: float) -> str:
    if score >= 0.75:
        return "strong"
    if score >= 0.55:
        return "plausible"
    if score >= 0.35:
        return "emerging"
    return "weak"


def _signal_weight(signal: HorizonSocialSignal) -> float:
    magnitude = min(abs(float(signal.normalized_score)) / 3.0, 1.0)
    return _clamp(signal.reliability) * magnitude


class HorizonCascadeService:
    ENGINE_VERSION = "horizon-human-response-cascade-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _stage_signal_map(pattern: HorizonBehaviorPattern, stages: list[str]) -> dict[int, set[str]]:
        mapping: dict[int, set[str]] = {index: set() for index in range(len(stages))}
        configured = (pattern.provenance or {}).get("stage_signal_types", {})
        if isinstance(configured, dict):
            for key, values in configured.items():
                try:
                    index = int(key)
                except (TypeError, ValueError):
                    try:
                        index = stages.index(str(key))
                    except ValueError:
                        continue
                if 0 <= index < len(stages) and isinstance(values, list):
                    mapping[index].update(str(item) for item in values)
        if not any(mapping.values()):
            required = [str(item) for item in (pattern.required_signal_types or [])]
            for index, signal_type in enumerate(required[: len(stages)]):
                mapping[index].add(signal_type)
        return mapping

    @staticmethod
    def _explicit_stage(signal: HorizonSocialSignal, stages: list[str]) -> int | None:
        evidence = signal.evidence or {}
        raw_index = evidence.get("cascade_stage_index")
        if isinstance(raw_index, int) and 0 <= raw_index < len(stages):
            return raw_index
        raw_stage = evidence.get("cascade_stage")
        if raw_stage is not None:
            normalized = str(raw_stage).strip().lower()
            for index, stage in enumerate(stages):
                if stage.strip().lower() == normalized:
                    return index
        return None

    @staticmethod
    def _acceleration(signals: list[HorizonSocialSignal]) -> float:
        if len(signals) < 2:
            return 0.0
        ordered = sorted(signals, key=lambda item: (item.observed_at, item.id))
        split = max(1, len(ordered) // 2)
        early = ordered[:split]
        late = ordered[split:]
        if not late:
            return 0.0
        early_mean = sum(_signal_weight(item) for item in early) / len(early)
        late_mean = sum(_signal_weight(item) for item in late) / len(late)
        # 0.5 = stable; >0.5 accelerating; <0.5 fading.
        return _clamp(0.5 + (late_mean - early_mean) / 2.0)

    def project(self, request: HorizonCascadeRequest) -> HorizonBehaviorCascade:
        now = datetime.utcnow()
        as_of = _utc_naive(request.as_of) if request.as_of else now
        if request.mode == "live" and as_of > now + timedelta(minutes=5):
            raise ValueError("live cascade as_of cannot be in the future")

        event = self.db.query(HorizonGlobalEvent).filter(
            HorizonGlobalEvent.id == request.event_id,
            HorizonGlobalEvent.status == "active",
        ).one_or_none()
        if event is None:
            raise ValueError("HORIZON event not found")
        if event.first_observed_at > as_of:
            raise ValueError("event was not observable at the requested cutoff")

        pattern = self.db.query(HorizonBehaviorPattern).filter(
            HorizonBehaviorPattern.id == request.pattern_id,
            HorizonBehaviorPattern.status == "active",
            HorizonBehaviorPattern.knowledge_available_at <= as_of,
        ).one_or_none()
        if pattern is None:
            raise ValueError("behavior pattern was not available at the requested cutoff")
        allowed = {str(item) for item in (pattern.event_types or [])}
        if allowed and "*" not in allowed and event.event_type not in allowed:
            raise ValueError("behavior pattern does not apply to this event type")

        signals = self.db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id == event.id,
            HorizonSocialSignal.observed_at <= as_of,
        ).order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc()).all()

        stages = [str(item) for item in (pattern.mechanism_chain or []) if str(item).strip()]
        if not stages:
            stages = ["collective response"]
        mapping = self._stage_signal_map(pattern, stages)
        assigned: dict[int, list[HorizonSocialSignal]] = {index: [] for index in range(len(stages))}
        unassigned: list[HorizonSocialSignal] = []

        for signal in signals:
            explicit = self._explicit_stage(signal, stages)
            if explicit is not None:
                assigned[explicit].append(signal)
                continue
            matched = [index for index, types in mapping.items() if signal.signal_type in types]
            if matched:
                assigned[min(matched)].append(signal)
            else:
                unassigned.append(signal)

        stage_snapshot = []
        frontier = -1
        continuity_broken = False
        for index, stage in enumerate(stages):
            evidence = assigned[index]
            if evidence:
                source_diversity = len({item.source for item in evidence})
                mean_weight = sum(_signal_weight(item) for item in evidence) / len(evidence)
                diversity_bonus = min(source_diversity / 3.0, 1.0) * 0.15
                score = _clamp(mean_weight * 0.85 + diversity_bonus)
            else:
                score = 0.0
            if score >= 0.70:
                state = "established"
            elif score >= 0.42:
                state = "active"
            elif score >= 0.18:
                state = "emerging"
            else:
                state = "latent"

            sequentially_reached = not continuity_broken and state in {"emerging", "active", "established"}
            if sequentially_reached:
                frontier = index
            elif state == "latent":
                continuity_broken = True

            stage_snapshot.append({
                "index": index,
                "stage": stage,
                "state": state,
                "score": round(score, 4),
                "sequentially_reached": sequentially_reached,
                "signal_types_expected": sorted(mapping[index]),
                "evidence_signal_keys": [item.signal_key for item in evidence],
                "source_diversity": len({item.source for item in evidence}),
            })

        current_index = max(frontier, 0)
        current_stage = stages[current_index] if frontier >= 0 else "pre-cascade / latent"
        next_index = frontier + 1
        next_stage = stages[next_index] if 0 <= next_index < len(stages) else ""
        stage_progress = (frontier + 1) / len(stages) if frontier >= 0 else 0.0
        all_assigned = [item for rows in assigned.values() for item in rows]
        signal_strength = (
            sum(_signal_weight(item) for item in all_assigned) / len(all_assigned)
            if all_assigned else 0.0
        )
        propagation = _clamp(0.65 * stage_progress + 0.35 * signal_strength)
        acceleration = self._acceleration(all_assigned)
        unique_sources = len({item.source for item in all_assigned})
        diversity = _clamp(unique_sources / 4.0)
        confidence = _clamp(
            0.45 * propagation
            + 0.20 * acceleration
            + 0.20 * diversity
            + 0.15 * _clamp(pattern.confidence)
        )

        key = sha256_dict({
            "engine": self.ENGINE_VERSION,
            "event_id": event.id,
            "pattern_id": pattern.id,
            "mode": request.mode,
            "as_of": as_of.isoformat(),
        })
        existing = self.db.query(HorizonBehaviorCascade).filter(
            HorizonBehaviorCascade.cascade_key == key
        ).one_or_none()
        if existing:
            return existing

        row = HorizonBehaviorCascade(
            cascade_key=key,
            event_id=event.id,
            pattern_id=pattern.id,
            mode=request.mode,
            as_of=as_of,
            stage_snapshot=stage_snapshot,
            evidence_snapshot=[{
                "signal_key": item.signal_key,
                "signal_type": item.signal_type,
                "source": item.source,
                "normalized_score": item.normalized_score,
                "reliability": item.reliability,
                "observed_at": item.observed_at.isoformat(),
            } for item in all_assigned],
            current_stage_index=float(frontier),
            current_stage=current_stage,
            next_stage=next_stage,
            propagation_score=round(propagation, 4),
            acceleration_score=round(acceleration, 4),
            evidence_diversity_score=round(diversity, 4),
            confidence_band=_band(confidence),
            probability_basis="not_calibrated",
            interpretation={
                "human_readable": (
                    f"Collective response appears to be at stage {frontier + 1}/{len(stages)}: {current_stage}."
                    if frontier >= 0 else "No sequential collective response stage is established yet."
                ),
                "next_transition": next_stage or None,
                "out_of_sequence_signal_count": sum(
                    len(assigned[index]) for index in range(frontier + 2, len(stages))
                ) if frontier + 2 < len(stages) else 0,
                "unassigned_signal_count": len(unassigned),
                "predictive_score_is_probability": False,
                "formal_probability_enabled": False,
            },
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
