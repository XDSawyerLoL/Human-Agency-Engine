from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..horizon_source_models import HorizonRawObservation
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService
from .horizon_world_pulse import FRED_OBSERVATIONS


FORECAST_API_ENDPOINT = "https://forecastapi.com/v2/forecast"


SOURCE_SPEC = HorizonSourceUpsert(
    source_key="forecastapi-fred-trajectory",
    name="ForecastAPI projections over official FRED series",
    source_class="model_forecast",
    adapter_kind="forecastapi_v2_fred_weekly",
    domains=["economy", "financial_conditions", "energy", "labor"],
    geography=["US", "GLOBAL"],
    base_locator=FORECAST_API_ENDPOINT,
    trust_weight=0.68,
    refresh_seconds=21600,
    requires_credentials=True,
    metadata_json={
        "role": "secondary_statistical_forecast",
        "independence_family": "fred-derived-model",
        "model_output_is_not_observed_fact": True,
        "forecast_interval_is_not_event_probability": True,
    },
)


SERIES_RULES = {
    "VIXCLS": {
        "label": "volatilité financière",
        "up_event": "financial_stress",
        "down_event": "financial_stress_easing",
        "up": lambda latest, path: max(path) >= max(25.0, latest + 4.0),
        "down": lambda latest, path: latest >= 20.0 and min(path) <= latest - 4.0,
    },
    "BAMLH0A0HYM2": {
        "label": "spread de crédit haut rendement",
        "up_event": "credit_stress",
        "down_event": "credit_stress_easing",
        "up": lambda latest, path: max(path) >= max(4.5, latest + 0.4),
        "down": lambda latest, path: latest >= 3.5 and min(path) <= latest - 0.35,
    },
    "DCOILWTICO": {
        "label": "prix du pétrole WTI",
        "up_event": "energy_price_spike",
        "down_event": "energy_price_relief",
        "up": lambda latest, path: latest > 0 and max(path) >= latest * 1.06,
        "down": lambda latest, path: latest > 0 and min(path) <= latest * 0.94,
    },
    "ICSA": {
        "label": "inscriptions initiales au chômage US",
        "up_event": "labor_market_softening",
        "down_event": "labor_market_improvement",
        "up": lambda latest, path: latest > 0 and max(path) >= latest * 1.10,
        "down": lambda latest, path: latest > 0 and min(path) <= latest * 0.90,
    },
}


def _weekly_points(observations: list[dict[str, Any]], max_points: int = 52) -> list[dict[str, Any]]:
    weeks: dict[date, tuple[date, float]] = {}
    for item in observations:
        raw_date = str(item.get("date") or "")
        raw_value = item.get("value")
        try:
            dt = date.fromisoformat(raw_date)
            value = float(raw_value)
        except (ValueError, TypeError):
            continue
        week = dt - timedelta(days=dt.weekday())
        previous = weeks.get(week)
        if previous is None or dt >= previous[0]:
            weeks[week] = (dt, value)
    ordered = sorted(weeks.items())[-max_points:]
    return [{"date": week.isoformat(), "value": value} for week, (_, value) in ordered]


class HorizonStatisticalForesightService:
    ENGINE_VERSION = "horizon-statistical-foresight-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db
        self.sources = HorizonSourceService(db)

    def poll(self, *, fred_api_key: str, forecast_api_key: str) -> dict[str, Any]:
        if not fred_api_key:
            return {"skipped": True, "reason": "FRED_API_KEY is not configured"}
        if not forecast_api_key:
            return {"skipped": True, "reason": "FORECAST_API_KEY/FORESCAST_API_KEY is not configured"}

        source = self.sources.upsert_source(SOURCE_SPEC)
        with httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
        ) as client:
            outcomes: list[dict[str, Any]] = []
            for series_id, rule in SERIES_RULES.items():
                try:
                    outcomes.append(
                        self._forecast_series(
                            client,
                            source,
                            series_id,
                            rule,
                            fred_api_key=fred_api_key,
                            forecast_api_key=forecast_api_key,
                        )
                    )
                except Exception as exc:
                    outcomes.append({"series_id": series_id, "ok": False, "error": str(exc)[:500]})
        return {
            "engine": self.ENGINE_VERSION,
            "series": outcomes,
            "forecast_calls": sum(int(row.get("forecast_call", False)) for row in outcomes),
            "candidate_ids": [row["candidate_id"] for row in outcomes if row.get("candidate_id")],
            "critical_semantics": {
                "forecastapi_value_interval_is_event_probability": False,
                "forecastapi_model_output_is_observed_fact": False,
                "fred_is_official_input_but_external_model_is_derived": True,
                "calls_are_deduplicated_by_latest_fred_week": True,
            },
        }

    def _forecast_series(
        self,
        client: httpx.Client,
        source,
        series_id: str,
        rule: dict[str, Any],
        *,
        fred_api_key: str,
        forecast_api_key: str,
    ) -> dict[str, Any]:
        fred = client.get(
            FRED_OBSERVATIONS,
            params={
                "series_id": series_id,
                "api_key": fred_api_key,
                "file_type": "json",
                "sort_order": "asc",
                "limit": 500,
            },
        )
        fred.raise_for_status()
        payload = fred.json()
        observations = payload.get("observations") if isinstance(payload, dict) else None
        if not isinstance(observations, list):
            raise ValueError("FRED returned no observation list")
        points = _weekly_points(observations)
        if len(points) < 12:
            raise ValueError(f"not enough weekly FRED points for {series_id}")

        latest = points[-1]
        forecast_key = f"forecastapi:{series_id}:{latest['date']}"
        existing = self.db.query(HorizonRawObservation).filter(
            HorizonRawObservation.source_id == source.id,
            HorizonRawObservation.external_key == forecast_key,
        ).one_or_none()
        if existing is not None:
            return {
                "series_id": series_id,
                "ok": True,
                "forecast_call": False,
                "replayed_observation_id": existing.id,
                "latest_week": latest["date"],
            }

        response = client.post(
            FORECAST_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {forecast_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "identifier": f"HORIZON-{series_id}",
                "tenant_context": "evidence-world-eye",
                "data": points,
                "periods": 4,
                "frequency": "W",
                "data_type": "financial_metric",
                "confidence_level": 0.80,
                "model": "standard",
            },
        )
        response.raise_for_status()
        forecast_payload = response.json()
        result = forecast_payload.get("result") if isinstance(forecast_payload, dict) else None
        forecasts = result.get("forecasts") if isinstance(result, dict) else None
        if not isinstance(forecasts, list):
            forecasts = forecast_payload.get("forecasts") if isinstance(forecast_payload, dict) else None
        if not isinstance(forecasts, list) or not forecasts:
            raise ValueError("ForecastAPI returned no forecast rows")

        path: list[float] = []
        sanitized_rows: list[dict[str, Any]] = []
        for row in forecasts:
            if not isinstance(row, dict):
                continue
            try:
                forecast = float(row.get("forecast", row.get("value")))
            except (TypeError, ValueError):
                continue
            path.append(forecast)
            sanitized_rows.append({
                "period": row.get("period"),
                "date": row.get("date"),
                "forecast": round(forecast, 6),
                "lower": row.get("lower"),
                "upper": row.get("upper"),
            })
        if not path:
            raise ValueError("ForecastAPI forecast rows contained no numeric path")

        model_info = result.get("model_info") if isinstance(result, dict) and isinstance(result.get("model_info"), dict) else {}
        observation, _ = self.sources.ingest_observation(
            source,
            HorizonObservationIngest(
                external_key=forecast_key,
                observation_type="secondary_time_series_forecast",
                title=f"Projection statistique {series_id} sur 4 semaines",
                summary=f"ForecastAPI projette la série FRED {series_id}; ce résultat est un signal de modèle, pas un fait observé.",
                source_url="https://fred.stlouisfed.org/series/" + series_id,
                geography=["US", "GLOBAL"],
                canonical_facts={
                    "series_id": series_id,
                    "latest_week": latest["date"],
                    "latest_value": latest["value"],
                    "forecast_path": sanitized_rows,
                    "model_output": True,
                    "intervals_are_value_intervals_not_event_probability": True,
                },
                raw_metadata={
                    "forecast_provider": "ForecastAPI",
                    "best_model": model_info.get("best_model"),
                    "selection_metric": model_info.get("selection_metric"),
                    "input_provider": "FRED",
                },
                event_time=None,
                published_at=None,
                observed_at=datetime.now(timezone.utc),
            ),
        )

        latest_value = float(latest["value"])
        event_type = None
        direction = "stable"
        if bool(rule["up"](latest_value, path)):
            event_type = str(rule["up_event"])
            direction = "up"
        elif bool(rule["down"](latest_value, path)):
            event_type = str(rule["down_event"])
            direction = "down"

        candidate_id = None
        if event_type:
            candidate = self.sources.build_candidate(
                HorizonCandidateBuild(
                    observation_ids=[observation.id],
                    event_type=event_type,
                    title=f"Trajectoire projetée : {rule['label']} ({direction})",
                    geography=["US", "GLOBAL"],
                    normalized_facts={
                        "series_id": series_id,
                        "latest_value": latest_value,
                        "forecast_values": path,
                        "forecast_horizon_weeks": 4,
                        "secondary_model_signal": True,
                        "direction": direction,
                    },
                    normalizer_version=self.ENGINE_VERSION,
                )
            )
            candidate_id = candidate.id

        return {
            "series_id": series_id,
            "ok": True,
            "forecast_call": True,
            "latest_week": latest["date"],
            "latest_value": latest_value,
            "forecast_values": [round(value, 6) for value in path],
            "direction": direction,
            "candidate_id": candidate_id,
            "observation_id": observation.id,
        }
