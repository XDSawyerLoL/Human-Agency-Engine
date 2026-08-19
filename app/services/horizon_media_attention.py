from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math

import httpx
from sqlalchemy.orm import Session

from ..horizon_behavioral_signal_schemas import HorizonMediaAttentionRefreshRequest
from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_source_models import HorizonSource
from .horizon_live import GDELT_DOC_ENDPOINT, _parse_seen_date
from .horizon_sources import HorizonSourceService


EVENT_QUERIES = {
    "extreme_heat": '(heatwave OR "extreme heat" OR "heat warning")',
    "strong_wind": '("strong wind" OR windstorm OR gale)',
    "heavy_rain": '("heavy rain" OR "torrential rain" OR downpour)',
    "thunderstorm": '(thunderstorm OR thunderstorms OR "severe storm")',
    "flood": '(flood OR flooding OR "flash flood")',
    "snow_ice": '(snowstorm OR blizzard OR "freezing rain" OR ice)',
    "extreme_cold": '("extreme cold" OR "cold wave" OR "cold snap")',
    "avalanche": '(avalanche OR avalanches)',
    "coastal_flood": '("coastal flooding" OR "storm surge" OR "coastal flood")',
    "supply_disruption": '(shortage OR shortages OR "supply disruption" OR rationing)',
    "fuel_supply_disruption": '("fuel shortage" OR "petrol shortage" OR "gasoline shortage" OR "fuel rationing")',
    "critical_goods_disruption": '(shortage OR shortages OR rationing OR "supply disruption")',
}

COUNTRY_QUERY_TERMS = {
    "FR": "France",
    "ES": "Spain",
    "DE": "Germany",
    "IT": "Italy",
    "GB": "Britain",
    "US": "USA",
}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _query_for_event(event: HorizonGlobalEvent) -> str | None:
    base = EVENT_QUERIES.get(event.event_type)
    if base is None:
        return None
    geography = [str(item).upper() for item in (event.geography or [])]
    country_terms = [COUNTRY_QUERY_TERMS[item] for item in geography if item in COUNTRY_QUERY_TERMS]
    if len(country_terms) == 1:
        return f"{base} {country_terms[0]}"
    return base


def _timeline_points(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    timeline = payload.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return []
    series = timeline[0]
    if not isinstance(series, dict):
        return []
    data = series.get("data")
    if not isinstance(data, list):
        return []
    points = []
    for item in data:
        if not isinstance(item, dict):
            continue
        observed = _parse_seen_date(item.get("date"))
        try:
            count = float(item.get("value", 0.0))
            norm = float(item.get("norm", 0.0))
        except (TypeError, ValueError):
            continue
        if observed is None or norm <= 0 or count < 0:
            continue
        points.append({"at": observed, "count": count, "norm": norm})
    points.sort(key=lambda item: item["at"])
    return points


def _share(points: list[dict]) -> float:
    count = sum(float(item["count"]) for item in points)
    norm = sum(float(item["norm"]) for item in points)
    return count / norm if norm > 0 else 0.0


class HorizonMediaAttentionService:
    ENGINE_VERSION = "horizon-gdelt-media-attention-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _gdelt_source(self) -> HorizonSource:
        HorizonSourceService(self.db).sync_builtin_sources()
        source = self.db.query(HorizonSource).filter(
            HorizonSource.source_key == "gdelt-doc-2"
        ).one()
        if not source.enabled:
            raise ValueError("GDELT source is disabled")
        return source

    def _events(self, request: HorizonMediaAttentionRefreshRequest) -> list[HorizonGlobalEvent]:
        query = self.db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.status == "active")
        if request.event_ids:
            query = query.filter(HorizonGlobalEvent.id.in_(request.event_ids))
        else:
            cutoff = datetime.utcnow() - timedelta(days=14)
            query = query.filter(HorizonGlobalEvent.first_observed_at >= cutoff)
        return (
            query.order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
            .limit(request.max_events)
            .all()
        )

    def refresh(
        self,
        request: HorizonMediaAttentionRefreshRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        source = self._gdelt_source()
        events = self._events(request)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=False,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        diagnostics = []
        created_signal_ids = []
        replayed_signal_ids = []
        try:
            for event in events:
                gdelt_query = _query_for_event(event)
                if gdelt_query is None:
                    diagnostics.append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "status": "unsupported_event_type",
                    })
                    continue
                try:
                    response = client.get(
                        GDELT_DOC_ENDPOINT,
                        params={
                            "query": gdelt_query,
                            "mode": "timelinevolraw",
                            "format": "json",
                            "timespan": f"{request.lookback_hours}h",
                            "timelinesmooth": 0,
                        },
                    )
                    response.raise_for_status()
                    points = _timeline_points(response.json())
                except (httpx.HTTPError, ValueError) as exc:
                    diagnostics.append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "status": "upstream_error",
                        "error": str(exc)[:300],
                    })
                    continue

                if len(points) < request.recent_intervals + 4:
                    diagnostics.append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "status": "insufficient_timeline",
                        "point_count": len(points),
                    })
                    continue

                recent = points[-request.recent_intervals:]
                baseline = points[:-request.recent_intervals]
                recent_count = sum(item["count"] for item in recent)
                baseline_count = sum(item["count"] for item in baseline)
                recent_share = _share(recent)
                baseline_share = _share(baseline)
                if baseline_share <= 0:
                    diagnostics.append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "status": "baseline_insufficient",
                        "recent_count": recent_count,
                        "baseline_count": baseline_count,
                    })
                    continue

                ratio = recent_share / baseline_share
                diagnostic = {
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "status": "below_signal_threshold",
                    "query": gdelt_query,
                    "recent_count": round(recent_count, 3),
                    "baseline_count": round(baseline_count, 3),
                    "recent_share": recent_share,
                    "baseline_share": baseline_share,
                    "attention_ratio": ratio,
                    "attention_ratio_is_probability": False,
                    "last_interval_at": recent[-1]["at"].isoformat(),
                }
                if recent_count < request.min_recent_articles or ratio < request.min_ratio:
                    diagnostics.append(diagnostic)
                    continue

                normalized_score = min(10.0, max(0.0, math.log2(ratio) * 2.0))
                volume_support = min(recent_count / 25.0, 1.0)
                reliability = min(
                    float(source.trust_weight),
                    float(source.trust_weight) * (0.60 + 0.40 * volume_support),
                )
                point_at = _utc_naive(recent[-1]["at"])
                signal_key = "media-attention:" + sha256(
                    (
                        f"{self.ENGINE_VERSION}|{event.id}|{gdelt_query}|"
                        f"{recent[-1]['at'].isoformat()}|{round(ratio, 6)}"
                    ).encode("utf-8")
                ).hexdigest()[:48]
                existing = self.db.query(HorizonSocialSignal).filter(
                    HorizonSocialSignal.signal_key == signal_key
                ).one_or_none()
                if existing is not None:
                    replayed_signal_ids.append(existing.id)
                    diagnostic["status"] = "replayed"
                    diagnostic["signal_id"] = existing.id
                    diagnostics.append(diagnostic)
                    continue

                signal = HorizonSocialSignal(
                    event_id=event.id,
                    signal_key=signal_key,
                    signal_type="media_attention",
                    source="gdelt-doc-2:timelinevolraw",
                    geography=event.geography,
                    value=recent_share,
                    baseline=baseline_share,
                    normalized_score=round(normalized_score, 4),
                    direction="up",
                    reliability=round(reliability, 4),
                    evidence={
                        "engine": self.ENGINE_VERSION,
                        "metric": "share_of_gdelt_monitored_coverage",
                        "query": gdelt_query,
                        "recent_intervals": request.recent_intervals,
                        "baseline_intervals": len(baseline),
                        "recent_article_count": recent_count,
                        "baseline_article_count": baseline_count,
                        "recent_monitored_articles": sum(item["norm"] for item in recent),
                        "baseline_monitored_articles": sum(item["norm"] for item in baseline),
                        "attention_ratio": ratio,
                        "ratio_is_probability": False,
                        "does_not_measure": [
                            "purchase_behavior",
                            "public_opinion",
                            "event_probability",
                        ],
                    },
                    observed_at=point_at,
                )
                self.db.add(signal)
                self.db.commit()
                self.db.refresh(signal)
                created_signal_ids.append(signal.id)
                diagnostic["status"] = "signal_created"
                diagnostic["signal_id"] = signal.id
                diagnostic["normalized_score"] = signal.normalized_score
                diagnostic["reliability"] = signal.reliability
                diagnostics.append(diagnostic)
        finally:
            if owned_client:
                client.close()

        return {
            "engine": self.ENGINE_VERSION,
            "events_scanned": len(events),
            "signals_created": len(created_signal_ids),
            "signals_replayed": len(replayed_signal_ids),
            "created_signal_ids": created_signal_ids,
            "diagnostics": diagnostics,
            "signal_semantics": "media_attention_acceleration_only",
            "formal_probability": False,
        }
