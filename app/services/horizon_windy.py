from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

import httpx
from sqlalchemy.orm import Session

from ..horizon_source_models import HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest
from ..horizon_windy_schemas import HorizonWindyPollRequest
from ..horizon_provisional_schemas import HorizonProvisionalRefreshRequest
from .horizon_provisional import HorizonProvisionalService
from .horizon_sources import HorizonSourceService
from .policy import sha256_dict


WINDY_POINT_FORECAST_ENDPOINT = "https://api.windy.com/api/point-forecast/v2"


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _timestamp(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)


def _temperature_c(value: float | int | None, unit: object) -> float | None:
    if value is None:
        return None
    result = float(value)
    normalized = str(unit or "").strip().lower()
    if normalized in {"k", "kelvin"} or (not normalized and result > 170.0):
        result -= 273.15
    return round(result, 3)


def _finite(values: list[object]) -> list[float]:
    result: list[float] = []
    for item in values:
        try:
            if item is not None:
                result.append(float(item))
        except (TypeError, ValueError):
            continue
    return result


def summarize_model_payload(payload: object, *, horizon_hours: int, observed_at: datetime) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Windy response is not a JSON object")
    raw_ts = payload.get("ts")
    if not isinstance(raw_ts, list) or not raw_ts:
        raise ValueError("Windy response contains no forecast timestamps")
    units = payload.get("units") if isinstance(payload.get("units"), dict) else {}
    deadline = observed_at + timedelta(hours=horizon_hours)

    temp_values = payload.get("temp-surface")
    if not isinstance(temp_values, list):
        raise ValueError("Windy response contains no temp-surface series")
    if len(temp_values) != len(raw_ts):
        raise ValueError("Windy timestamp and temperature arrays have different lengths")

    rows: list[dict] = []
    for index, raw in enumerate(raw_ts):
        at = _timestamp(raw)
        if at < observed_at - timedelta(hours=3) or at > deadline:
            continue
        temp_c = _temperature_c(temp_values[index], units.get("temp-surface"))
        if temp_c is None:
            continue
        rows.append({"at": at, "temp_c": temp_c})
    if not rows:
        raise ValueError("Windy response contains no usable temperatures inside requested horizon")

    peak = max(rows, key=lambda item: (item["temp_c"], -item["at"].timestamp()))
    gusts = _finite(payload.get("gust-surface", []) if isinstance(payload.get("gust-surface"), list) else [])
    precipitation = _finite(
        payload.get("past3hprecip-surface", []) if isinstance(payload.get("past3hprecip-surface"), list) else []
    )
    return {
        "forecast_points": len(rows),
        "forecast_start": rows[0]["at"].isoformat(),
        "forecast_end": rows[-1]["at"].isoformat(),
        "max_temp_c": peak["temp_c"],
        "max_temp_at": peak["at"].isoformat(),
        "max_gust": round(max(gusts), 3) if gusts else None,
        "precip_sum_raw": round(sum(precipitation), 3) if precipitation else None,
        "units": units,
    }


class HorizonWindyService:
    ENGINE_VERSION = "horizon-windy-weather-dynamics-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        HorizonSourceService(self.db).sync_builtin_sources()
        source = self.db.query(HorizonSource).filter(
            HorizonSource.source_key == "windy-point-forecast"
        ).one()
        if not source.enabled:
            raise ValueError("Windy Point Forecast source is disabled")
        if source.adapter_kind != "windy_point_forecast_v2":
            raise ValueError("Windy source adapter kind is not approved")
        return source

    def poll(
        self,
        request: HorizonWindyPollRequest,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        key = api_key.strip()
        if not key:
            raise ValueError("WINDY_POINT_FORECAST_API_KEY is not configured")
        source = self._source()
        now = observed_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(25.0),
                follow_redirects=False,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
            )

        source_service = HorizonSourceService(self.db)
        model_rows: list[dict] = []
        observation_ids: list[int] = []
        errors: list[dict] = []
        try:
            for model in request.models:
                body = {
                    "lat": round(request.lat, 4),
                    "lon": round(request.lon, 4),
                    "model": model,
                    "parameters": request.parameters,
                    "levels": ["surface"],
                    "key": key,
                }
                try:
                    response = client.post(WINDY_POINT_FORECAST_ENDPOINT, json=body)
                    if response.status_code == 204:
                        errors.append({"model": model, "error": "no requested parameters available"})
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    summary = summarize_model_payload(
                        payload,
                        horizon_hours=request.horizon_hours,
                        observed_at=now,
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append({"model": model, "error": str(exc)[:300]})
                    continue

                fingerprint = sha256_dict(
                    {
                        "model": model,
                        "lat": round(request.lat, 2),
                        "lon": round(request.lon, 2),
                        "payload": payload,
                    }
                )
                minute_bucket = now.replace(second=0, microsecond=0)
                observation = HorizonObservationIngest(
                    external_key=(
                        f"windy:{model}:{round(request.lat, 2)}:{round(request.lon, 2)}:"
                        f"{minute_bucket.strftime('%Y%m%d%H%M')}:{fingerprint[:24]}"
                    ),
                    observation_type="weather_model_forecast",
                    title=f"Windy {model} forecast at {request.lat:.2f}, {request.lon:.2f}",
                    summary=(
                        f"Machine forecast snapshot from {model}; HORIZON treats model output as a precursor, "
                        "not as an observed weather fact."
                    ),
                    source_url=WINDY_POINT_FORECAST_ENDPOINT,
                    geography=request.geography,
                    canonical_facts={
                        "model": model,
                        "lat": round(request.lat, 4),
                        "lon": round(request.lon, 4),
                        "summary": summary,
                        "forecast_payload": payload,
                    },
                    raw_metadata={
                        "engine": self.ENGINE_VERSION,
                        "provider": "Windy Point Forecast API v2",
                        "provider_data_is_ground_truth": False,
                        "historical_forecast_retrieval_supported": False,
                        "ecmwf_point_forecast_used": False,
                    },
                    event_time=_timestamp(payload["ts"][0]),
                    published_at=now,
                    observed_at=now,
                )
                row, created = source_service.ingest_observation(source, observation)
                observation_ids.append(row.id)
                model_rows.append(
                    {
                        "model": model,
                        "observation_id": row.id,
                        "observation_created": created,
                        **summary,
                    }
                )
        finally:
            if owned_client:
                client.close()

        heat_rows = [
            item for item in model_rows
            if float(item["max_temp_c"]) >= float(request.heat_watch_threshold_c)
        ]
        candidate_id = None
        heat_consensus = None
        if len(heat_rows) >= 2:
            peaks = [float(item["max_temp_c"]) for item in heat_rows]
            peak_times = [datetime.fromisoformat(str(item["max_temp_at"])) for item in heat_rows]
            model_spread = max(peaks) - min(peaks)
            time_spread_hours = (max(peak_times) - min(peak_times)).total_seconds() / 3600.0
            heat_consensus = {
                "supporting_models": [item["model"] for item in heat_rows],
                "supporting_model_count": len(heat_rows),
                "median_peak_temp_c": round(float(median(peaks)), 3),
                "peak_temp_spread_c": round(model_spread, 3),
                "peak_time_spread_hours": round(time_spread_hours, 3),
                "target_window_start": min(peak_times).isoformat(),
                "target_window_end": max(peak_times).isoformat(),
                "threshold_c": request.heat_watch_threshold_c,
                "max_allowed_spread_c": request.max_heat_model_spread_c,
            }
            if model_spread <= request.max_heat_model_spread_c and time_spread_hours <= 24.0:
                candidate = source_service.build_candidate(
                    HorizonCandidateBuild(
                        observation_ids=sorted(set(item["observation_id"] for item in heat_rows)),
                        event_type="extreme_heat",
                        title=f"Windy multi-model extreme-heat watch at {request.lat:.2f}, {request.lon:.2f}",
                        geography=request.geography,
                        normalized_facts={
                            "forecast_only": True,
                            "provider": "windy",
                            "models": [item["model"] for item in heat_rows],
                            "lat": round(request.lat, 4),
                            "lon": round(request.lon, 4),
                            "heat_consensus": heat_consensus,
                            "forecast_target_window": {
                                "start": min(peak_times).isoformat(),
                                "end": max(peak_times).isoformat(),
                            },
                            "geography_status": "known" if request.geography else "unknown",
                            "confirmation_status": "unconfirmed_model_forecast",
                        },
                        normalizer_version=self.ENGINE_VERSION,
                    )
                )
                candidate_id = candidate.id

        provisional = None
        if candidate_id is not None:
            provisional = HorizonProvisionalService(self.db).refresh(
                HorizonProvisionalRefreshRequest(max_candidates=100)
            )

        return {
            "engine": self.ENGINE_VERSION,
            "source_key": source.source_key,
            "observed_at": _utc_naive(now).isoformat(),
            "location": {"lat": request.lat, "lon": request.lon, "geography": request.geography},
            "models_requested": request.models,
            "models_succeeded": len(model_rows),
            "model_snapshots": model_rows,
            "errors": errors,
            "heat_consensus": heat_consensus,
            "candidate_id": candidate_id,
            "provisional_refresh": provisional,
            "critical_semantics": {
                "windy_is_official_confirmation": False,
                "windy_is_model_forecast_precursor": True,
                "model_consensus_is_probability": False,
                "candidate_auto_promoted": False,
                "historical_forecast_retrieval_supported": False,
                "numeric_probabilities_enabled": False,
            },
        }
