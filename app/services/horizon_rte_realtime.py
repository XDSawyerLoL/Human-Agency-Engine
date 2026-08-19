from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from ..horizon_convergence_schemas import HorizonRteRealtimePollRequest
from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


RTE_REALTIME_DATASET = "eco2mix-regional-tr"
RTE_REALTIME_ENDPOINT = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    f"{RTE_REALTIME_DATASET}/records"
)
PARIS_TZ = ZoneInfo("Europe/Paris")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _region_code(event: HorizonGlobalEvent) -> str | None:
    facts = event.raw_facts or {}
    value = str(facts.get("region_code") or "").strip()
    if value:
        return value
    for item in event.geography or []:
        text = str(item).upper().strip()
        if text.startswith("REGION:"):
            return text.split(":", 1)[1]
    return None


def _weekday_class(day: date) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


class HorizonRteRealtimeService:
    ENGINE_VERSION = "horizon-rte-regional-realtime-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key="rte-eco2mix-regional-tr",
                name="RTE eco2mix regional realtime",
                source_class="official_statistical",
                adapter_kind="odre_eco2mix_regional_realtime_v2",
                domains=["electricity", "consumption", "behavioral_signals", "realtime"],
                geography=["FR"],
                base_locator=RTE_REALTIME_ENDPOINT,
                trust_weight=0.86,
                refresh_seconds=3600,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "near_live_regional_collective_load_sensor",
                    "evidence_roles": ["behavioral_outcome", "physical_state"],
                    "dataset_id": RTE_REALTIME_DATASET,
                    "provider_refresh": "hourly",
                    "provider_time_step": "15_minutes",
                    "provider_depth": "month_minus_2_to_h_minus_2",
                    "data_quality": "telemetry_plus_estimates_not_final_metering",
                    "negative_label_authority": False,
                },
            )
        )
        if not source.enabled:
            raise ValueError("RTE regional realtime source is disabled")
        return source

    def _active_regions(self, request: HorizonRteRealtimePollRequest, as_of: datetime) -> tuple[list[str], list[HorizonGlobalEvent]]:
        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == "extreme_heat_region",
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at <= _utc_naive(as_of),
            )
            .order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
            .all()
        )
        recent_cutoff = _utc_naive(as_of - timedelta(days=10))
        events = [event for event in events if event.first_observed_at >= recent_cutoff]
        requested = set(request.region_codes)
        if requested:
            events = [event for event in events if _region_code(event) in requested]
            regions = sorted(requested)
        else:
            regions = sorted({code for event in events if (code := _region_code(event))})
        return regions, events

    def _fetch_region(
        self,
        client: httpx.Client,
        region_code: str,
        *,
        start_at: datetime,
        end_at: datetime,
        max_records: int,
    ) -> tuple[list[dict], bool]:
        where = (
            f'code_insee_region = "{region_code}" '
            f"and date_heure >= date'{start_at.astimezone(timezone.utc).isoformat()}' "
            f"and date_heure <= date'{end_at.astimezone(timezone.utc).isoformat()}' "
            "and consommation is not null"
        )
        rows: list[dict] = []
        offset = 0
        truncated = False
        while len(rows) < max_records:
            limit = min(100, max_records - len(rows))
            response = client.get(
                RTE_REALTIME_ENDPOINT,
                params={
                    "select": "code_insee_region,libelle_region,date_heure,consommation,nature",
                    "where": where,
                    "order_by": "date_heure asc",
                    "limit": limit,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                raise ValueError("RTE realtime response contains no results array")
            rows.extend(item for item in results if isinstance(item, dict))
            if len(results) < limit:
                break
            offset += len(results)
        if len(rows) >= max_records:
            truncated = True
        return rows, truncated

    @staticmethod
    def _metric(records: list[dict], request: HorizonRteRealtimePollRequest) -> dict | None:
        points: list[tuple[datetime, float]] = []
        for record in records:
            at = _parse_datetime(record.get("date_heure"))
            if at is None:
                continue
            try:
                value = float(record.get("consommation"))
            except (TypeError, ValueError):
                continue
            points.append((at, value))
        points.sort(key=lambda item: item[0])
        if len(points) < request.rolling_points * 3:
            return None

        latest_at = points[-1][0]
        latest_local = latest_at.astimezone(PARIS_TZ)
        target_minutes = latest_local.hour * 60 + latest_local.minute
        latest_day = latest_local.date()
        same_day = [
            (at, value)
            for at, value in points
            if at.astimezone(PARIS_TZ).date() == latest_day and at <= latest_at
        ]
        current_window = same_day[-request.rolling_points :]
        if len(current_window) < request.rolling_points:
            return None
        current_mean = sum(value for _, value in current_window) / len(current_window)

        points_by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
        for at, value in points:
            local = at.astimezone(PARIS_TZ)
            if local.date() >= latest_day:
                continue
            if latest_day - local.date() > timedelta(days=request.baseline_days):
                continue
            if _weekday_class(local.date()) != _weekday_class(latest_day):
                continue
            point_minutes = local.hour * 60 + local.minute
            if target_minutes - 15 * (request.rolling_points - 1) <= point_minutes <= target_minutes:
                points_by_day[local.date()].append((at, value))

        comparable_means: list[float] = []
        for day, day_points in sorted(points_by_day.items()):
            day_points.sort(key=lambda item: item[0])
            if len(day_points) < request.rolling_points:
                continue
            window = day_points[-request.rolling_points :]
            comparable_means.append(sum(value for _, value in window) / len(window))
        if len(comparable_means) < 2:
            return None
        baseline = float(median(comparable_means))
        if baseline <= 0:
            return None
        lift = (current_mean - baseline) / baseline
        return {
            "latest_at": latest_at,
            "latest_local_time": latest_local.isoformat(),
            "rolling_points": request.rolling_points,
            "window_minutes": request.rolling_points * 15,
            "current_mean_mw": current_mean,
            "baseline_median_mw": baseline,
            "comparable_days": len(comparable_means),
            "lift_ratio": lift,
        }

    def poll(
        self,
        request: HorizonRteRealtimePollRequest,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        source = self._source()
        as_of = observed_at or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        regions, active_events = self._active_regions(request, as_of)
        if not regions:
            return {
                "source_key": source.source_key,
                "regions_requested": [],
                "active_regional_heat_events": 0,
                "new_observations": 0,
                "signals_created": 0,
                "skipped": True,
                "reason": "no active or explicitly requested region",
                "critical_semantics": {
                    "realtime_data_is_final_metering": False,
                    "signal_authorizes_negative_backtest_label": False,
                    "signal_is_probability": False,
                },
            }

        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(25.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        created_observations: list[int] = []
        replayed_observations: list[int] = []
        signal_ids: list[int] = []
        results: list[dict] = []
        errors: list[dict] = []
        start_at = as_of - timedelta(days=request.baseline_days + 1)
        metric_spec_id = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "baseline_days": request.baseline_days,
                "rolling_points": request.rolling_points,
                "minimum_lift_ratio": request.minimum_lift_ratio,
            }
        )[:16]
        try:
            for region_code in regions:
                try:
                    rows, truncated = self._fetch_region(
                        client,
                        region_code,
                        start_at=start_at,
                        end_at=as_of,
                        max_records=request.max_records_per_region,
                    )
                    metric = self._metric(rows, request)
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"region_code": region_code, "error": str(exc)[:300]})
                    continue
                if metric is None:
                    results.append({
                        "region_code": region_code,
                        "records_fetched": len(rows),
                        "metric_available": False,
                        "truncated": truncated,
                    })
                    continue

                latest_at = metric["latest_at"]
                identity = sha256_dict(
                    {
                        "metric_spec_id": metric_spec_id,
                        "region_code": region_code,
                        "latest_at": latest_at.isoformat(),
                        "current_mean_mw": round(metric["current_mean_mw"], 3),
                        "baseline_median_mw": round(metric["baseline_median_mw"], 3),
                    }
                )[:32]
                external_key = f"rte-regional-realtime:{region_code}:{identity}"
                existing = self.db.query(HorizonRawObservation).filter(
                    HorizonRawObservation.source_id == source.id,
                    HorizonRawObservation.external_key == external_key,
                ).one_or_none()
                if existing is None:
                    observation = HorizonObservationIngest(
                        external_key=external_key,
                        observation_type="regional_electricity_load_realtime",
                        title=f"RTE charge régionale quasi-live — région {region_code}",
                        summary="Charge électrique régionale récente comparée à des créneaux horaires comparables récents.",
                        source_url=RTE_REALTIME_ENDPOINT,
                        geography=["FR", f"REGION:{region_code}"],
                        canonical_facts={
                            "metric_spec_id": metric_spec_id,
                            "region_code": region_code,
                            "latest_at": latest_at.isoformat(),
                            "latest_local_time": metric["latest_local_time"],
                            "window_minutes": metric["window_minutes"],
                            "current_mean_mw": round(metric["current_mean_mw"], 3),
                            "baseline_median_mw": round(metric["baseline_median_mw"], 3),
                            "comparable_days": metric["comparable_days"],
                            "lift_ratio": round(metric["lift_ratio"], 6),
                            "minimum_lift_ratio": request.minimum_lift_ratio,
                        },
                        raw_metadata={
                            "engine": self.ENGINE_VERSION,
                            "dataset_id": RTE_REALTIME_DATASET,
                            "provider_values_include_estimates": True,
                            "final_metering": False,
                            "negative_label_authority": False,
                            "records_fetched": len(rows),
                            "truncated": truncated,
                        },
                        event_time=latest_at,
                        published_at=latest_at,
                        observed_at=as_of,
                    )
                    observation_row, _ = HorizonSourceService(self.db).ingest_observation(source, observation)
                    created_observations.append(observation_row.id)
                else:
                    observation_row = existing
                    replayed_observations.append(existing.id)

                linked = 0
                if float(metric["lift_ratio"]) >= float(request.minimum_lift_ratio):
                    for event in active_events:
                        if _region_code(event) != region_code:
                            continue
                        signal_key = (
                            f"rte-cooling-load-live:{metric_spec_id}:{event.id}:{identity}"
                        )
                        existing_signal = self.db.query(HorizonSocialSignal).filter(
                            HorizonSocialSignal.signal_key == signal_key
                        ).one_or_none()
                        if existing_signal is None:
                            score = min(3.0, float(metric["lift_ratio"]) / max(request.minimum_lift_ratio, 0.001))
                            signal = HorizonSocialSignal(
                                event_id=event.id,
                                signal_key=signal_key,
                                signal_type="cooling_load_pressure_live",
                                source=source.source_key,
                                geography=["FR", f"REGION:{region_code}"],
                                value=round(metric["current_mean_mw"], 3),
                                baseline=round(metric["baseline_median_mw"], 3),
                                normalized_score=round(score, 4),
                                direction="up",
                                reliability=0.82,
                                evidence={
                                    "raw_observation_id": observation_row.id,
                                    "metric_spec_id": metric_spec_id,
                                    "lift_ratio": round(metric["lift_ratio"], 6),
                                    "threshold_ratio": request.minimum_lift_ratio,
                                    "realtime_estimate": True,
                                    "final_materialization_label": False,
                                    "cooling_causality_proven": False,
                                },
                                observed_at=_utc_naive(latest_at),
                            )
                            self.db.add(signal)
                            self.db.flush()
                            signal_ids.append(signal.id)
                            linked += 1
                        else:
                            signal_ids.append(existing_signal.id)
                    self.db.commit()

                results.append({
                    "region_code": region_code,
                    "records_fetched": len(rows),
                    "metric_available": True,
                    "latest_at": latest_at.isoformat(),
                    "lift_ratio": round(metric["lift_ratio"], 6),
                    "above_threshold": float(metric["lift_ratio"]) >= float(request.minimum_lift_ratio),
                    "signals_linked": linked,
                    "truncated": truncated,
                })
        finally:
            if owned_client:
                client.close()

        return {
            "engine": self.ENGINE_VERSION,
            "source_key": source.source_key,
            "dataset_id": RTE_REALTIME_DATASET,
            "regions_requested": regions,
            "active_regional_heat_events": len(active_events),
            "metric_spec_id": metric_spec_id,
            "new_observations": len(set(created_observations)),
            "replayed_observations": len(set(replayed_observations)),
            "signals_created_or_reused": len(set(signal_ids)),
            "regions": results,
            "errors": errors,
            "critical_semantics": {
                "realtime_data_is_final_metering": False,
                "realtime_signal_is_behavioral_proxy": True,
                "realtime_signal_is_final_materialization_label": False,
                "signal_authorizes_negative_backtest_label": False,
                "cooling_causality_proven": False,
                "signal_is_probability": False,
            },
        }
