from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from ..horizon_backfill_models import HorizonHistoricalBackfillRun
from ..horizon_backfill_schemas import HorizonRteCoolingLoadBackfillRequest
from ..horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from ..horizon_source_models import HorizonSource
from ..horizon_source_schemas import HorizonObservationIngest, HorizonSourceUpsert
from .horizon_coverage import HorizonHistoricalCoverageService
from .horizon_heat_regions import HorizonRegionalHeatService
from .horizon_response_library import HorizonResponseLibraryService
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


RTE_REGIONAL_DATASET = "eco2mix-regional-cons-def"
RTE_REGIONAL_ENDPOINT = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    f"{RTE_REGIONAL_DATASET}/records"
)
RTE_AVAILABLE_FROM = datetime(2013, 1, 1)
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


def _local_date_and_hour(value: datetime) -> tuple[date, int]:
    local = value.astimezone(PARIS_TZ)
    return local.date(), local.hour


def _weekday_class(day: date) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


def _event_region_code(event: HorizonGlobalEvent) -> str | None:
    facts = event.raw_facts or {}
    value = str(facts.get("region_code") or "").strip()
    if value:
        return value
    for item in event.geography or []:
        text = str(item).upper().strip()
        if text.startswith("REGION:"):
            return text.split(":", 1)[1]
    return None


class HorizonRteCoolingLoadBackfillService:
    ENGINE_VERSION = "horizon-rte-cooling-load-backfill-v0.1"
    ADAPTER_KIND = "odre_eco2mix_regional_v2"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key="rte-eco2mix-regional-cons-def",
                name="RTE eco2mix regional consolidated and definitive",
                source_class="official_statistical",
                adapter_kind=self.ADAPTER_KIND,
                domains=["electricity", "consumption", "behavioral_outcomes", "historical_archive"],
                geography=["FR"],
                base_locator=RTE_REGIONAL_ENDPOINT,
                trust_weight=0.94,
                refresh_seconds=86400,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "official_historical_regional_electricity_consumption_outcome_stream",
                    "dataset_id": RTE_REGIONAL_DATASET,
                    "temporal_depth_from": "2013-01-01",
                    "signal_scope": ["cooling_load_pressure"],
                },
            )
        )
        if not source.enabled:
            raise ValueError("RTE regional eco2mix source is disabled")
        return source

    @staticmethod
    def _serialize_run(row: HorizonHistoricalBackfillRun, *, replayed: bool) -> dict:
        result = dict(row.result_snapshot or {})
        result.update(
            {
                "run_id": row.id,
                "run_key": row.run_key,
                "created_at": row.created_at.isoformat(),
                "replayed_existing_run": replayed,
            }
        )
        return result

    @staticmethod
    def _daily_metrics(records: list[dict], request: HorizonRteCoolingLoadBackfillRequest) -> dict[date, dict]:
        points_by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
        for record in records:
            at = _parse_datetime(record.get("date_heure"))
            if at is None:
                continue
            try:
                consumption = float(record.get("consommation"))
            except (TypeError, ValueError):
                continue
            local_day, local_hour = _local_date_and_hour(at)
            if 12 <= local_hour < 20:
                points_by_day[local_day].append((at, consumption))

        valid_means: dict[date, dict] = {}
        for day, points in sorted(points_by_day.items()):
            if len(points) < request.minimum_afternoon_points:
                continue
            values = [value for _, value in points]
            valid_means[day] = {
                "mean_consumption_mw": sum(values) / len(values),
                "point_count": len(points),
                "last_observed_at": max(at for at, _ in points),
                "weekday_class": _weekday_class(day),
            }

        result: dict[date, dict] = {}
        for day in sorted(valid_means):
            start = day - timedelta(days=request.baseline_lookback_days)
            comparables = [
                metrics["mean_consumption_mw"]
                for previous_day, metrics in valid_means.items()
                if start <= previous_day < day
                and metrics["weekday_class"] == valid_means[day]["weekday_class"]
            ]
            if len(comparables) < 4:
                continue
            baseline = float(median(comparables))
            if baseline <= 0:
                continue
            actual = float(valid_means[day]["mean_consumption_mw"])
            lift = (actual - baseline) / baseline
            result[day] = {
                **valid_means[day],
                "baseline_median_mw": baseline,
                "baseline_comparable_days": len(comparables),
                "lift_ratio": lift,
            }
        return result

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
            f"and date_heure >= date'{start_at.replace(tzinfo=timezone.utc).isoformat()}' "
            f"and date_heure <= date'{end_at.replace(tzinfo=timezone.utc).isoformat()}' "
            "and consommation is not null"
        )
        rows: list[dict] = []
        offset = 0
        truncated = False
        while len(rows) < max_records:
            page_size = min(100, max_records - len(rows))
            response = client.get(
                RTE_REGIONAL_ENDPOINT,
                params={
                    "select": "code_insee_region,libelle_region,date_heure,consommation,nature",
                    "where": where,
                    "order_by": "date_heure asc",
                    "limit": page_size,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                raise ValueError("RTE OpenDataSoft response contains no results array")
            rows.extend(item for item in results if isinstance(item, dict))
            if len(results) < page_size:
                break
            offset += len(results)
        if len(rows) >= max_records:
            truncated = True
        return rows, truncated

    def backfill(
        self,
        request: HorizonRteCoolingLoadBackfillRequest,
        *,
        client: httpx.Client | None = None,
    ) -> dict:
        start_at = _utc_naive(request.start_at)
        end_at = _utc_naive(request.end_at)
        if start_at < RTE_AVAILABLE_FROM:
            raise ValueError("RTE regional eco2mix consolidated history is used from 2013-01-01")
        if end_at > datetime.utcnow() + timedelta(minutes=5):
            raise ValueError("historical RTE backfill end_at cannot be in the future")
        if end_at - start_at > timedelta(days=366):
            raise ValueError("one RTE historical backfill run is limited to 366 days")

        source = self._source()
        # A real backfill must leave the matching behavior prior available for the
        # Backtest Factory; syncing is idempotent and built-in pattern versions are immutable.
        HorizonResponseLibraryService(self.db).sync_builtins()
        regionalization = HorizonRegionalHeatService(self.db).aggregate(
            start_at=start_at,
            end_at=end_at,
        )
        events = (
            self.db.query(HorizonGlobalEvent)
            .filter(
                HorizonGlobalEvent.event_type == "extreme_heat_region",
                HorizonGlobalEvent.status == "active",
                HorizonGlobalEvent.first_observed_at <= end_at,
            )
            .order_by(HorizonGlobalEvent.first_observed_at.asc(), HorizonGlobalEvent.id.asc())
            .all()
        )
        relevant_events = []
        for event in events:
            facts = event.raw_facts or {}
            episode_start = _parse_datetime(facts.get("episode_start"))
            episode_end = _parse_datetime(facts.get("episode_end"))
            if episode_start is None or episode_end is None:
                continue
            episode_start_naive = _utc_naive(episode_start)
            episode_end_naive = _utc_naive(episode_end)
            if episode_end_naive < start_at or episode_start_naive > end_at:
                continue
            relevant_events.append(event)

        region_codes = sorted({code for event in relevant_events if (code := _event_region_code(event))})
        lookback_start = start_at - timedelta(days=request.baseline_lookback_days + 7)
        metric_spec_id = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "metric": "regional_afternoon_load_vs_recent_weekday_class_median",
                "baseline_lookback_days": request.baseline_lookback_days,
                "minimum_afternoon_points": request.minimum_afternoon_points,
                "minimum_lift_ratio": request.minimum_lift_ratio,
            }
        )[:16]
        fingerprint = sha256_dict(
            {
                "engine": self.ENGINE_VERSION,
                "source_id": source.id,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "regions": region_codes,
                "request": request.model_dump(mode="json"),
                "metric_spec_id": metric_spec_id,
                "regional_event_ids": [event.id for event in relevant_events],
            }
        )
        run_key = fingerprint
        existing = self.db.query(HorizonHistoricalBackfillRun).filter(
            HorizonHistoricalBackfillRun.run_key == run_key
        ).one_or_none()
        if existing is not None:
            return self._serialize_run(existing, replayed=True)

        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        source_service = HorizonSourceService(self.db)
        coverage_service = HorizonHistoricalCoverageService(self.db)
        observation_ids: list[int] = []
        signal_ids: list[int] = []
        coverage_ids: list[int] = []
        errors: list[dict] = []
        region_results: list[dict] = []
        try:
            for region_code in region_codes:
                try:
                    records, truncated = self._fetch_region(
                        client,
                        region_code,
                        start_at=lookback_start,
                        end_at=end_at,
                        max_records=request.max_records,
                    )
                    daily = self._daily_metrics(records, request)
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"region_code": region_code, "error": str(exc)[:300]})
                    continue

                region_events = [event for event in relevant_events if _event_region_code(event) == region_code]
                signal_days = 0
                days_with_metric = 0
                target_days = []
                cursor = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
                while cursor <= end_at:
                    target_days.append(cursor.date())
                    cursor += timedelta(days=1)
                complete_days = [day for day in target_days if day in daily]
                coverage_complete = not truncated and len(complete_days) == len(target_days)

                for day in sorted(day for day in daily if start_at.date() <= day <= end_at.date()):
                    metrics = daily[day]
                    days_with_metric += 1
                    observed_at = metrics["last_observed_at"]
                    observation = HorizonObservationIngest(
                        external_key=(
                            f"rte-regional-cooling:{metric_spec_id}:{region_code}:{day.isoformat()}"
                        ),
                        observation_type="regional_electricity_consumption_outcome",
                        title=f"RTE charge électrique région {region_code} — {day.isoformat()}",
                        summary=(
                            "Moyenne de consommation électrique régionale de l'après-midi comparée à une "
                            "médiane historique récente de jours comparables."
                        ),
                        source_url=RTE_REGIONAL_ENDPOINT,
                        geography=["FR", f"REGION:{region_code}"],
                        canonical_facts={
                            "metric_spec_id": metric_spec_id,
                            "region_code": region_code,
                            "local_date": day.isoformat(),
                            "afternoon_mean_consumption_mw": round(metrics["mean_consumption_mw"], 3),
                            "baseline_median_mw": round(metrics["baseline_median_mw"], 3),
                            "lift_ratio": round(metrics["lift_ratio"], 6),
                            "point_count": metrics["point_count"],
                            "baseline_comparable_days": metrics["baseline_comparable_days"],
                            "baseline_lookback_days": request.baseline_lookback_days,
                            "minimum_afternoon_points": request.minimum_afternoon_points,
                            "minimum_lift_ratio": request.minimum_lift_ratio,
                        },
                        raw_metadata={
                            "engine": self.ENGINE_VERSION,
                            "dataset_id": RTE_REGIONAL_DATASET,
                            "metric_spec_id": metric_spec_id,
                            "metric": "12:00-20:00 Europe/Paris mean vs recent weekday/weekend-class median",
                            "cooling_causality_proven": False,
                            "archive_is_consolidated": True,
                            "physical_load_was_realtime_observable": True,
                        },
                        event_time=observed_at,
                        published_at=observed_at,
                        observed_at=observed_at,
                    )
                    observation_row, _ = source_service.ingest_observation(source, observation)
                    observation_ids.append(observation_row.id)

                    if float(metrics["lift_ratio"]) < float(request.minimum_lift_ratio):
                        continue
                    for event in region_events:
                        facts = event.raw_facts or {}
                        episode_end = _parse_datetime(facts.get("episode_end"))
                        if episode_end is None:
                            continue
                        outcome_deadline = _utc_naive(episode_end) + timedelta(hours=96)
                        observed_naive = _utc_naive(observed_at)
                        if observed_naive <= event.first_observed_at or observed_naive > outcome_deadline:
                            continue
                        signal_key = (
                            f"rte-cooling-load:{metric_spec_id}:{event.id}:{region_code}:{day.isoformat()}"
                        )
                        existing_signal = self.db.query(HorizonSocialSignal).filter(
                            HorizonSocialSignal.signal_key == signal_key
                        ).one_or_none()
                        if existing_signal is not None:
                            signal_ids.append(existing_signal.id)
                            continue
                        score = min(3.0, float(metrics["lift_ratio"]) / float(request.minimum_lift_ratio))
                        signal = HorizonSocialSignal(
                            event_id=event.id,
                            signal_key=signal_key,
                            signal_type="cooling_load_pressure",
                            source=source.source_key,
                            geography=["FR", f"REGION:{region_code}"],
                            value=round(metrics["mean_consumption_mw"], 3),
                            baseline=round(metrics["baseline_median_mw"], 3),
                            normalized_score=round(score, 4),
                            direction="up",
                            reliability=0.94,
                            evidence={
                                "raw_observation_id": observation_row.id,
                                "metric_spec_id": metric_spec_id,
                                "region_code": region_code,
                                "local_date": day.isoformat(),
                                "lift_ratio": round(metrics["lift_ratio"], 6),
                                "threshold_ratio": request.minimum_lift_ratio,
                                "cooling_causality_proven": False,
                                "interpretation": "regional afternoon electricity load pressure consistent with increased cooling demand",
                            },
                            observed_at=_utc_naive(observed_at),
                        )
                        self.db.add(signal)
                        self.db.flush()
                        signal_ids.append(signal.id)
                        signal_days += 1
                self.db.commit()

                coverage = coverage_service.record_interval(
                    source,
                    coverage_kind="signal",
                    event_types=["extreme_heat_region"],
                    signal_types=["cooling_load_pressure"],
                    geography=["FR", f"REGION:{region_code}"],
                    start_at=start_at,
                    end_at=end_at,
                    completeness="complete" if coverage_complete else "partial",
                    basis="rte_regional_half_hour_consumption_with_baseline_metric_available_each_calendar_day",
                    provenance={
                        "engine": self.ENGINE_VERSION,
                        "dataset_id": RTE_REGIONAL_DATASET,
                        "metric_spec_id": metric_spec_id,
                        "records_fetched": len(records),
                        "truncated": truncated,
                        "target_calendar_days": len(target_days),
                        "days_with_valid_baseline_metric": len(complete_days),
                        "baseline_lookback_days": request.baseline_lookback_days,
                        "minimum_afternoon_points": request.minimum_afternoon_points,
                        "minimum_lift_ratio": request.minimum_lift_ratio,
                        "absence_under_complete_coverage_can_authorize_negative_label": True,
                        "cooling_causality_proven": False,
                    },
                )
                coverage_ids.append(coverage.id)
                region_results.append(
                    {
                        "region_code": region_code,
                        "metric_spec_id": metric_spec_id,
                        "records_fetched": len(records),
                        "days_with_metric": days_with_metric,
                        "elevated_signal_links_created_or_reused": signal_days,
                        "coverage_complete": coverage_complete,
                        "coverage_interval_id": coverage.id,
                        "truncated": truncated,
                    }
                )
        finally:
            if owned_client:
                client.close()

        result = {
            "engine": self.ENGINE_VERSION,
            "adapter": self.ADAPTER_KIND,
            "source_key": source.source_key,
            "metric_spec_id": metric_spec_id,
            "window": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            "regionalization": regionalization,
            "regional_heat_events_considered": len(relevant_events),
            "region_codes": region_codes,
            "raw_outcome_observations_created_or_reused": len(set(observation_ids)),
            "cooling_load_signal_links_created_or_reused": len(set(signal_ids)),
            "coverage_interval_ids": coverage_ids,
            "regions": region_results,
            "errors": errors,
            "critical_semantics": {
                "rte_consumption_is_behavioral_outcome_proxy": True,
                "rte_load_proves_air_conditioning_causality": False,
                "department_heat_compared_directly_to_national_load": False,
                "regional_heat_requires_multiple_departments": True,
                "derived_metric_identity_includes_configuration": True,
                "negative_labels_require_complete_signal_coverage": True,
                "numeric_probabilities_enabled": False,
            },
        }
        run = HorizonHistoricalBackfillRun(
            run_key=run_key,
            engine_version=self.ENGINE_VERSION,
            adapter_kind=self.ADAPTER_KIND,
            source_id=source.id,
            requested_start_at=start_at,
            requested_end_at=end_at,
            request_snapshot=request.model_dump(mode="json"),
            result_snapshot=result,
            status="completed_with_errors" if errors else "completed",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return self._serialize_run(run, replayed=False)
