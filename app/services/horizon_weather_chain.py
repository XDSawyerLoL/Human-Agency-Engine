from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_provisional_models import HorizonProvisionalForecast, HorizonProvisionalResolution
from ..horizon_source_models import HorizonEventCandidate
from ..horizon_weather_chain_models import HorizonWeatherImpactChain
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc_naive(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc_naive(parsed)


def _candidate_local_geography(candidate: HorizonEventCandidate) -> set[str]:
    return {
        str(item).upper().strip()
        for item in (candidate.geography or [])
        if str(item).strip() and str(item).upper().strip() not in {"FR", "*"}
    }


def _event_domain_id(event: HorizonGlobalEvent) -> str:
    normalized = (event.raw_facts or {}).get("normalized_facts") or {}
    if isinstance(normalized, dict):
        domain_id = str(normalized.get("domain_id") or "").upper().strip()
        if domain_id:
            return domain_id
    for item in event.geography or []:
        value = str(item).upper().strip()
        if value not in {"FR", "*"} and not value.startswith("REGION:"):
            return value
    return ""


def _candidate_target_window(candidate: HorizonEventCandidate) -> tuple[datetime, datetime] | None:
    normalized = candidate.normalized_facts or {}
    if not isinstance(normalized, dict):
        return None
    window = normalized.get("forecast_target_window") or {}
    if not isinstance(window, dict):
        return None
    start = _parse_datetime(window.get("start"))
    end = _parse_datetime(window.get("end"))
    if start is None or end is None:
        return None
    if end < start:
        start, end = end, start
    return start, end


def _official_validity_window(event: HorizonGlobalEvent) -> tuple[datetime, datetime] | None:
    normalized = (event.raw_facts or {}).get("normalized_facts") or {}
    if not isinstance(normalized, dict):
        return None
    period = normalized.get("period") or {}
    if not isinstance(period, dict):
        return None
    start = _parse_datetime(period.get("begin_validity_time"))
    end = _parse_datetime(period.get("end_validity_time"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _windows_overlap(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1])


class HorizonWeatherChainService:
    ENGINE_VERSION = "horizon-windy-confirmation-impact-chain-v0.1"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _is_windy_forecast_candidate(candidate: HorizonEventCandidate) -> bool:
        normalized = candidate.normalized_facts or {}
        return bool(
            isinstance(normalized, dict)
            and normalized.get("forecast_only") is True
            and str(normalized.get("provider") or "").lower() == "windy"
        )

    def _official_match(self, candidate: HorizonEventCandidate) -> HorizonGlobalEvent | None:
        local_geography = _candidate_local_geography(candidate)
        target_window = _candidate_target_window(candidate)
        if not local_geography or target_window is None:
            return None

        rows = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == candidate.event_type,
                HorizonGlobalEvent.source == "meteofrance-vigilance",
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at > candidate.first_observed_at,
                HorizonGlobalEvent.first_observed_at <= target_window[1],
            )
            .order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .all()
        )
        for event in rows:
            domain_id = _event_domain_id(event)
            if not domain_id or domain_id not in local_geography:
                continue
            validity = _official_validity_window(event)
            if validity is None or not _windows_overlap(target_window, validity):
                continue
            return event
        return None

    def match_official_confirmations(self, *, max_forecasts: int = 1000) -> dict:
        unresolved = (
            self.db.query(HorizonProvisionalForecast)
            .outerjoin(
                HorizonProvisionalResolution,
                HorizonProvisionalResolution.forecast_id == HorizonProvisionalForecast.id,
            )
            .filter(HorizonProvisionalResolution.id.is_(None))
            .order_by(HorizonProvisionalForecast.as_of.asc(), HorizonProvisionalForecast.id.asc())
            .limit(max_forecasts)
            .all()
        )
        by_candidate: dict[int, list[HorizonProvisionalForecast]] = defaultdict(list)
        for forecast in unresolved:
            by_candidate[forecast.candidate_id].append(forecast)

        candidate_matches = 0
        resolutions_created = 0
        too_broad = 0
        waiting = 0
        hindsight_forecasts = 0
        matches: list[dict] = []
        for candidate_id, forecasts in sorted(by_candidate.items()):
            candidate = self.db.query(HorizonEventCandidate).filter(
                HorizonEventCandidate.id == candidate_id
            ).one_or_none()
            if candidate is None or not self._is_windy_forecast_candidate(candidate):
                continue
            if not _candidate_local_geography(candidate) or _candidate_target_window(candidate) is None:
                too_broad += 1
                continue
            event = self._official_match(candidate)
            if event is None:
                waiting += 1
                continue

            windy_at = _utc_naive(candidate.first_observed_at)
            confirmed_at = _utc_naive(event.first_observed_at)
            lead = (confirmed_at - windy_at).total_seconds() / 3600.0
            if lead <= 0:
                waiting += 1
                continue
            eligible_forecasts = [
                forecast
                for forecast in forecasts
                if _utc_naive(forecast.as_of) <= confirmed_at
                and _utc_naive(forecast.created_at) <= _utc_naive(event.created_at)
            ]
            hindsight_forecasts += len(forecasts) - len(eligible_forecasts)
            if not eligible_forecasts:
                waiting += 1
                continue

            candidate_matches += 1
            created_for_candidate: list[int] = []
            for forecast in eligible_forecasts:
                resolution = HorizonProvisionalResolution(
                    forecast_id=forecast.id,
                    resolution_type="matched_external_official_confirmation",
                    promoted_event_id=event.id,
                    corroborated_at=confirmed_at,
                    corroboration_lead_time_hours=round(lead, 3),
                    predictive_lead_time_hours=None,
                    evidence={
                        "engine": self.ENGINE_VERSION,
                        "candidate_key": candidate.candidate_key,
                        "confirmed_event_key": event.event_key,
                        "windy_candidate_was_promoted": False,
                        "official_source": event.source,
                        "geography_match": True,
                        "temporal_validity_overlap": True,
                        "forecast_existed_before_confirmation": True,
                        "lead_time_anchor": "windy_candidate.first_observed_at",
                        "corroboration_lead_time_is_predictive_outcome_lead": False,
                        "candidate_event_hypothesis_confirmed": True,
                        "behavioral_outcome_confirmed": False,
                    },
                )
                self.db.add(resolution)
                self.db.flush()
                resolutions_created += 1
                created_for_candidate.append(resolution.id)
            self.db.commit()
            matches.append(
                {
                    "candidate_id": candidate.id,
                    "confirmed_event_id": event.id,
                    "windy_first_observed_at": windy_at.isoformat(),
                    "official_confirmed_at": confirmed_at.isoformat(),
                    "windy_to_official_lead_hours": round(lead, 3),
                    "provisional_resolution_ids": created_for_candidate,
                }
            )

        return {
            "engine": self.ENGINE_VERSION,
            "provisional_forecasts_scanned": len(unresolved),
            "windy_candidates_matched": candidate_matches,
            "provisional_resolutions_created": resolutions_created,
            "provisional_forecasts_skipped_as_hindsight": hindsight_forecasts,
            "windy_candidates_waiting_for_official_confirmation": waiting,
            "windy_candidates_skipped_for_broad_or_missing_scope": too_broad,
            "matches": matches,
            "critical_semantics": {
                "windy_candidate_promoted_to_fact": False,
                "official_confirmation_required": True,
                "precise_local_geography_required": True,
                "forecast_and_warning_validity_must_overlap": True,
                "forecast_must_preexist_official_confirmation": True,
                "windy_to_official_lead_is_behavioral_predictive_lead": False,
            },
        }

    def _candidate_confirmation_map(self) -> dict[int, tuple[HorizonProvisionalResolution, HorizonGlobalEvent]]:
        rows = (
            self.db.query(HorizonProvisionalResolution, HorizonProvisionalForecast)
            .join(
                HorizonProvisionalForecast,
                HorizonProvisionalForecast.id == HorizonProvisionalResolution.forecast_id,
            )
            .filter(HorizonProvisionalResolution.resolution_type == "matched_external_official_confirmation")
            .order_by(HorizonProvisionalResolution.corroborated_at.asc(), HorizonProvisionalResolution.id.asc())
            .all()
        )
        result: dict[int, tuple[HorizonProvisionalResolution, HorizonGlobalEvent]] = {}
        for resolution, forecast in rows:
            if forecast.candidate_id in result or resolution.promoted_event_id is None:
                continue
            event = self.db.query(HorizonGlobalEvent).filter(
                HorizonGlobalEvent.id == resolution.promoted_event_id
            ).one_or_none()
            if event is not None:
                result[forecast.candidate_id] = (resolution, event)
        return result

    def refresh_impact_chains(self, *, max_chains: int = 1000) -> dict:
        confirmations = self._candidate_confirmation_map()
        created = 0
        waiting_for_region = 0
        waiting_for_behavior = 0
        chains: list[dict] = []

        regional_events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == "extreme_heat_region",
                HorizonGlobalEvent.status == "active",
            )
            .order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .all()
        )

        for candidate_id, (resolution, confirmed_event) in sorted(confirmations.items()):
            if created >= max_chains:
                break
            existing = self.db.query(HorizonWeatherImpactChain).filter(
                HorizonWeatherImpactChain.windy_candidate_id == candidate_id
            ).one_or_none()
            if existing is not None:
                continue
            candidate = self.db.query(HorizonEventCandidate).filter(
                HorizonEventCandidate.id == candidate_id
            ).one_or_none()
            if candidate is None:
                continue

            regional_event = None
            for event in regional_events:
                member_ids = (event.raw_facts or {}).get("member_event_ids") or []
                try:
                    normalized_ids = {int(item) for item in member_ids}
                except (TypeError, ValueError):
                    continue
                if confirmed_event.id in normalized_ids:
                    regional_event = event
                    break
            if regional_event is None:
                waiting_for_region += 1
                continue

            signal = (
                self.db.query(HorizonSocialSignal)
                .filter(
                    HorizonSocialSignal.event_id == regional_event.id,
                    HorizonSocialSignal.signal_type == "cooling_load_pressure",
                    HorizonSocialSignal.source == "rte-eco2mix-regional-cons-def",
                    HorizonSocialSignal.direction == "up",
                    HorizonSocialSignal.reliability >= 0.85,
                    HorizonSocialSignal.observed_at > confirmed_event.first_observed_at,
                )
                .order_by(HorizonSocialSignal.observed_at.asc(), HorizonSocialSignal.id.asc())
                .first()
            )
            if signal is None:
                waiting_for_behavior += 1
                continue

            windy_at = _utc_naive(candidate.first_observed_at)
            official_at = _utc_naive(confirmed_event.first_observed_at)
            behavior_at = _utc_naive(signal.observed_at)
            if not windy_at < official_at < behavior_at:
                continue
            windy_to_official = (official_at - windy_at).total_seconds() / 3600.0
            official_to_behavior = (behavior_at - official_at).total_seconds() / 3600.0
            windy_to_behavior = (behavior_at - windy_at).total_seconds() / 3600.0
            chain_key = sha256_dict(
                {
                    "engine": self.ENGINE_VERSION,
                    "windy_candidate_id": candidate.id,
                    "confirmed_event_id": confirmed_event.id,
                    "regional_event_id": regional_event.id,
                    "outcome_signal_id": signal.id,
                }
            )
            chain = HorizonWeatherImpactChain(
                chain_key=chain_key,
                windy_candidate_id=candidate.id,
                confirmed_event_id=confirmed_event.id,
                regional_event_id=regional_event.id,
                outcome_signal_id=signal.id,
                windy_first_observed_at=windy_at,
                official_confirmed_at=official_at,
                behavior_observed_at=behavior_at,
                windy_to_official_lead_hours=round(windy_to_official, 3),
                official_to_behavior_lag_hours=round(official_to_behavior, 3),
                windy_to_behavior_lead_hours=round(windy_to_behavior, 3),
                evidence={
                    "engine": self.ENGINE_VERSION,
                    "provisional_resolution_id": resolution.id,
                    "windy_candidate_key": candidate.candidate_key,
                    "confirmed_event_key": confirmed_event.event_key,
                    "regional_event_key": regional_event.event_key,
                    "outcome_signal_key": signal.signal_key,
                    "weather_hypothesis_confirmed_by_official_primary": True,
                    "behavioral_outcome_proxy_observed": True,
                    "behavioral_outcome_proxy": "regional_electricity_cooling_load_pressure",
                    "windy_caused_behavior": False,
                    "heat_causality_proven_by_rte_load": False,
                    "chain_is_causal_proof": False,
                    "formal_probability": False,
                },
            )
            self.db.add(chain)
            self.db.commit()
            self.db.refresh(chain)
            created += 1
            chains.append(self._serialize_chain(chain))

        return {
            "engine": self.ENGINE_VERSION,
            "confirmed_windy_candidates_scanned": len(confirmations),
            "impact_chains_created": created,
            "waiting_for_regional_heat_state": waiting_for_region,
            "waiting_for_behavioral_outcome": waiting_for_behavior,
            "chains": chains,
            "critical_semantics": {
                "windy_to_official_is_weather_confirmation_lead": True,
                "windy_to_behavior_is_observed_chain_lead": True,
                "windy_to_behavior_is_causal_proof": False,
                "rte_signal_is_behavioral_outcome_proxy": True,
                "numeric_probabilities_enabled": False,
            },
        }

    @staticmethod
    def _serialize_chain(row: HorizonWeatherImpactChain) -> dict:
        return {
            "id": row.id,
            "chain_key": row.chain_key,
            "windy_candidate_id": row.windy_candidate_id,
            "confirmed_event_id": row.confirmed_event_id,
            "regional_event_id": row.regional_event_id,
            "outcome_signal_id": row.outcome_signal_id,
            "windy_first_observed_at": row.windy_first_observed_at.isoformat(),
            "official_confirmed_at": row.official_confirmed_at.isoformat(),
            "behavior_observed_at": row.behavior_observed_at.isoformat(),
            "windy_to_official_lead_hours": row.windy_to_official_lead_hours,
            "official_to_behavior_lag_hours": row.official_to_behavior_lag_hours,
            "windy_to_behavior_lead_hours": row.windy_to_behavior_lead_hours,
            "evidence": row.evidence,
            "created_at": row.created_at.isoformat(),
        }

    def reconcile(self, *, max_forecasts: int = 1000, max_chains: int = 1000) -> dict:
        confirmations = self.match_official_confirmations(max_forecasts=max_forecasts)
        impacts = self.refresh_impact_chains(max_chains=max_chains)
        return {
            "engine": self.ENGINE_VERSION,
            "confirmation": confirmations,
            "impact": impacts,
        }

    def list_chains(self, *, limit: int = 200) -> list[dict]:
        rows = (
            self.db.query(HorizonWeatherImpactChain)
            .order_by(HorizonWeatherImpactChain.created_at.desc(), HorizonWeatherImpactChain.id.desc())
            .limit(limit)
            .all()
        )
        return [self._serialize_chain(row) for row in rows]
