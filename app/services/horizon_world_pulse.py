from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService


FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"
USGS_DAY_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
NOAA_KP_FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
COPERNICUS_CEMS_ACTIVATIONS = (
    "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/"
)


SOURCE_SPECS = {
    "fred-macro-pulse": HorizonSourceUpsert(
        source_key="fred-macro-pulse",
        name="Federal Reserve Economic Data macro pulse",
        source_class="official_statistical",
        adapter_kind="fred_series_observations_v1",
        domains=["economy", "financial_conditions", "energy", "labor"],
        geography=["US", "GLOBAL"],
        base_locator=FRED_OBSERVATIONS,
        trust_weight=0.95,
        refresh_seconds=1800,
        requires_credentials=True,
        metadata_json={
            "role": "official_macro_precursor_stream",
            "credential_policy": "server_secret_only",
            "derived_thresholds_are_not_official_forecasts": True,
        },
    ),
    "usgs-earthquake-live": HorizonSourceUpsert(
        source_key="usgs-earthquake-live",
        name="USGS real-time earthquake feed",
        source_class="official_primary",
        adapter_kind="usgs_earthquake_geojson",
        domains=["geophysics", "disaster", "infrastructure"],
        geography=["*"],
        base_locator=USGS_DAY_FEED,
        trust_weight=0.98,
        refresh_seconds=300,
        requires_credentials=False,
        metadata_json={"role": "official_seismic_event_detection"},
    ),
    "noaa-swpc-kp-forecast": HorizonSourceUpsert(
        source_key="noaa-swpc-kp-forecast",
        name="NOAA SWPC planetary K-index forecast",
        source_class="model_forecast",
        adapter_kind="noaa_swpc_kp_forecast_json",
        domains=["space_weather", "satellite", "navigation", "power_grid"],
        geography=["GLOBAL"],
        base_locator=NOAA_KP_FORECAST,
        trust_weight=0.90,
        refresh_seconds=900,
        requires_credentials=False,
        metadata_json={
            "role": "official_space_weather_forecast_not_observed_event",
            "forecast_only": True,
        },
    ),
    "copernicus-cems-rapid-mapping": HorizonSourceUpsert(
        source_key="copernicus-cems-rapid-mapping",
        name="Copernicus EMS Rapid Mapping activations",
        source_class="official_multilateral",
        adapter_kind="copernicus_cems_public_activations_json",
        domains=["disaster", "humanitarian", "earth_observation"],
        geography=["*"],
        base_locator=COPERNICUS_CEMS_ACTIVATIONS,
        trust_weight=0.95,
        refresh_seconds=900,
        requires_credentials=False,
        metadata_json={
            "role": "official_multilateral_emergency_activation_stream",
            "public_endpoint_requires_api_key": False,
        },
    ),
}


FRED_SERIES = {
    "VIXCLS": {
        "event_type": "financial_stress",
        "label": "Volatilité financière",
        "trigger": lambda values: values[0] >= 25.0 or values[0] - values[min(5, len(values) - 1)] >= 7.0,
    },
    "BAMLH0A0HYM2": {
        "event_type": "credit_stress",
        "label": "Tension du crédit à haut rendement",
        "trigger": lambda values: values[0] >= 4.5 or values[0] - values[min(5, len(values) - 1)] >= 0.75,
    },
    "DCOILWTICO": {
        "event_type": "energy_price_spike",
        "label": "Hausse rapide du pétrole WTI",
        "trigger": lambda values: values[min(5, len(values) - 1)] > 0
        and (values[0] / values[min(5, len(values) - 1)] - 1.0) >= 0.08,
    },
    "ICSA": {
        "event_type": "labor_market_softening",
        "label": "Dégradation rapide des inscriptions au chômage US",
        "trigger": lambda values: len(values) >= 5
        and mean(values[1:5]) > 0
        and (values[0] / mean(values[1:5]) - 1.0) >= 0.15,
    },
}


CEMS_EVENT_TYPES = {
    "flood": "flood_emergency",
    "wildfire": "wildfire_emergency",
    "fire": "wildfire_emergency",
    "storm": "severe_storm_emergency",
    "earthquake": "major_earthquake",
    "volcano": "volcanic_emergency",
    "volcanic": "volcanic_emergency",
    "drought": "drought_emergency",
}


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class HorizonWorldPulseService:
    ENGINE_VERSION = "horizon-world-pulse-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db
        self.sources = HorizonSourceService(db)

    def _source(self, key: str):
        return self.sources.upsert_source(SOURCE_SPECS[key])

    def _candidate(
        self,
        observation_id: int,
        *,
        event_type: str,
        title: str,
        geography: list[str],
        facts: dict[str, Any],
        promote: bool = False,
    ) -> tuple[int, int | None]:
        candidate = self.sources.build_candidate(
            HorizonCandidateBuild(
                observation_ids=[observation_id],
                event_type=event_type,
                title=title[:255],
                geography=geography,
                normalized_facts=facts,
                normalizer_version=self.ENGINE_VERSION,
            )
        )
        event_id = None
        if promote:
            readiness = self.sources.promotion_readiness(candidate)
            if readiness.get("ready"):
                event_id = self.sources.promote_candidate(candidate).id
        return candidate.id, event_id

    def poll(self, *, fred_api_key: str = "") -> dict[str, Any]:
        with httpx.Client(
            timeout=httpx.Timeout(25.0),
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
        ) as client:
            results = [
                self._safe("usgs", lambda: self.poll_usgs(client)),
                self._safe("noaa_swpc", lambda: self.poll_noaa_swpc(client)),
                self._safe("copernicus_cems", lambda: self.poll_copernicus_cems(client)),
            ]
            if fred_api_key:
                results.append(self._safe("fred", lambda: self.poll_fred(client, fred_api_key)))
            else:
                results.append({"name": "fred", "ok": False, "skipped": True, "reason": "FRED_API_KEY is not configured"})
        return {
            "engine": self.ENGINE_VERSION,
            "sources": results,
            "succeeded": sum(1 for item in results if item.get("ok") is True),
            "failed": sum(1 for item in results if item.get("ok") is False and not item.get("skipped")),
            "skipped": sum(1 for item in results if item.get("skipped")),
            "critical_semantics": {
                "derived_threshold_is_not_official_forecast": True,
                "model_forecast_is_not_observed_event": True,
                "official_event_can_seed_downstream_forecast": True,
            },
        }

    @staticmethod
    def _safe(name: str, fn) -> dict[str, Any]:
        try:
            return {"name": name, "ok": True, "result": fn()}
        except Exception as exc:
            return {"name": name, "ok": False, "error": str(exc)[:500]}

    def poll_fred(self, client: httpx.Client, api_key: str) -> dict[str, Any]:
        source = self._source("fred-macro-pulse")
        created = 0
        candidates: list[int] = []
        triggered: list[str] = []
        for series_id, spec in FRED_SERIES.items():
            response = client.get(
                FRED_OBSERVATIONS,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 20,
                },
            )
            response.raise_for_status()
            payload = response.json()
            observations = payload.get("observations") if isinstance(payload, dict) else None
            if not isinstance(observations, list):
                raise ValueError(f"FRED {series_id} returned no observations")
            usable: list[tuple[str, float]] = []
            for item in observations:
                try:
                    value = float(item.get("value"))
                except (TypeError, ValueError):
                    continue
                usable.append((str(item.get("date") or ""), value))
            if len(usable) < 2:
                continue
            latest_date, latest_value = usable[0]
            obs, is_new = self.sources.ingest_observation(
                source,
                HorizonObservationIngest(
                    external_key=f"fred:{series_id}:{latest_date}:{latest_value}",
                    observation_type="macro_statistical_observation",
                    title=f"FRED {series_id} = {latest_value}",
                    summary=str(spec["label"]),
                    source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    geography=["US", "GLOBAL"],
                    canonical_facts={
                        "series_id": series_id,
                        "value": latest_value,
                        "date": latest_date,
                        "recent_values": [value for _, value in usable[:6]],
                    },
                    raw_metadata={"provider": "Federal Reserve Bank of St. Louis"},
                    event_time=_parse_dt(f"{latest_date}T00:00:00Z"),
                    published_at=None,
                    observed_at=datetime.now(timezone.utc),
                ),
            )
            created += int(is_new)
            values = [value for _, value in usable]
            if bool(spec["trigger"](values)):
                candidate_id, _ = self._candidate(
                    obs.id,
                    event_type=str(spec["event_type"]),
                    title=f"{spec['label']} — signal FRED {series_id}",
                    geography=["US", "GLOBAL"],
                    facts={
                        "series_id": series_id,
                        "latest_value": latest_value,
                        "recent_values": values[:6],
                        "derived_threshold_signal": True,
                        "official_forecast": False,
                    },
                )
                candidates.append(candidate_id)
                triggered.append(series_id)
        return {"new_observations": created, "candidate_ids": candidates, "triggered_series": triggered}

    def poll_usgs(self, client: httpx.Client) -> dict[str, Any]:
        source = self._source("usgs-earthquake-live")
        response = client.get(USGS_DAY_FEED)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list):
            raise ValueError("USGS feed returned no features")
        now = datetime.now(timezone.utc)
        created = 0
        events: list[int] = []
        for feature in features:
            props = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(props, dict):
                continue
            try:
                mag = float(props.get("mag"))
                event_ms = float(props.get("time"))
            except (TypeError, ValueError):
                continue
            if mag < 5.5:
                continue
            event_time = datetime.fromtimestamp(event_ms / 1000.0, tz=timezone.utc)
            if event_time < now - timedelta(hours=36):
                continue
            event_id_raw = str(feature.get("id") or "").strip()
            if not event_id_raw:
                continue
            place = str(props.get("place") or "zone non précisée")
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else []
            obs, is_new = self.sources.ingest_observation(
                source,
                HorizonObservationIngest(
                    external_key=f"usgs:{event_id_raw}",
                    observation_type="earthquake_observation",
                    title=f"Séisme M{mag:.1f} — {place}",
                    summary="Séisme significatif détecté par le flux temps réel USGS.",
                    source_url=str(props.get("url") or ""),
                    geography=[place],
                    canonical_facts={
                        "magnitude": mag,
                        "place": place,
                        "coordinates": coordinates,
                        "tsunami_flag": props.get("tsunami"),
                        "significance": props.get("sig"),
                    },
                    raw_metadata={"usgs_event_id": event_id_raw},
                    event_time=event_time,
                    published_at=event_time,
                    observed_at=now,
                ),
            )
            created += int(is_new)
            _, promoted = self._candidate(
                obs.id,
                event_type="major_earthquake",
                title=f"Séisme M{mag:.1f} — {place}",
                geography=[place],
                facts={"magnitude": mag, "place": place, "tsunami_flag": props.get("tsunami")},
                promote=True,
            )
            if promoted is not None:
                events.append(promoted)
        return {"new_observations": created, "promoted_event_ids": sorted(set(events))}

    def poll_noaa_swpc(self, client: httpx.Client) -> dict[str, Any]:
        source = self._source("noaa-swpc-kp-forecast")
        response = client.get(NOAA_KP_FORECAST)
        response.raise_for_status()
        payload = response.json()
        rows: list[dict[str, Any]] = []
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            rows = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, list) and payload and isinstance(payload[0], list):
            headers = [str(item) for item in payload[0]]
            rows = [dict(zip(headers, item)) for item in payload[1:] if isinstance(item, list)]
        if not rows:
            raise ValueError("NOAA SWPC Kp forecast returned no rows")
        now = datetime.now(timezone.utc)
        future: list[tuple[datetime, float, Any]] = []
        for row in rows:
            at = _parse_dt(row.get("time_tag"))
            try:
                kp = float(row.get("kp"))
            except (TypeError, ValueError):
                continue
            observed_flag = str(row.get("observed") or "").lower()
            if at and at >= now - timedelta(hours=1) and observed_flag not in {"observed", "estimated"}:
                future.append((at, kp, row.get("noaa_scale")))
        if not future:
            return {"forecast_rows": 0, "max_kp": None, "candidate_id": None}
        peak = max(future, key=lambda item: item[1])
        if peak[1] < 5.0:
            return {"forecast_rows": len(future), "max_kp": peak[1], "candidate_id": None}
        obs, _ = self.sources.ingest_observation(
            source,
            HorizonObservationIngest(
                external_key=f"swpc-kp:{peak[0].isoformat()}:{peak[1]:.1f}",
                observation_type="space_weather_model_forecast",
                title=f"NOAA SWPC prévoit un pic Kp {peak[1]:.1f}",
                summary="Prévision officielle de météo spatiale ; ce n’est pas encore un événement observé.",
                source_url=NOAA_KP_FORECAST,
                geography=["GLOBAL"],
                canonical_facts={
                    "max_kp": peak[1],
                    "peak_at": peak[0].isoformat(),
                    "noaa_scale": peak[2],
                    "forecast_only": True,
                },
                raw_metadata={"provider": "NOAA SWPC"},
                event_time=peak[0],
                published_at=None,
                observed_at=now,
            ),
        )
        candidate_id, _ = self._candidate(
            obs.id,
            event_type="geomagnetic_storm_risk",
            title=f"Risque de tempête géomagnétique — pic Kp {peak[1]:.1f}",
            geography=["GLOBAL"],
            facts={"max_kp": peak[1], "peak_at": peak[0].isoformat(), "forecast_only": True},
        )
        return {"forecast_rows": len(future), "max_kp": peak[1], "candidate_id": candidate_id}

    def poll_copernicus_cems(self, client: httpx.Client) -> dict[str, Any]:
        source = self._source("copernicus-cems-rapid-mapping")
        response = client.get(COPERNICUS_CEMS_ACTIVATIONS, params={"limit": 50})
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("Copernicus CEMS returned no activations")
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        created = 0
        candidates: list[int] = []
        for item in rows:
            if not isinstance(item, dict) or item.get("closed") is True:
                continue
            activation_time = _parse_dt(item.get("activationTime"))
            if activation_time is None or activation_time < cutoff:
                continue
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or code or "Activation Copernicus CEMS")
            category = str(item.get("category") or "").lower()
            countries = [str(x) for x in (item.get("countries") or []) if str(x).strip()]
            event_type = "large_disaster_activation"
            for token, mapped in CEMS_EVENT_TYPES.items():
                if token in category:
                    event_type = mapped
                    break
            obs, is_new = self.sources.ingest_observation(
                source,
                HorizonObservationIngest(
                    external_key=f"cems:{code}:{item.get('lastUpdate') or activation_time.isoformat()}",
                    observation_type="emergency_mapping_activation",
                    title=name,
                    summary=f"Activation Copernicus EMS Rapid Mapping — {category or 'catégorie non précisée'}.",
                    source_url=f"https://mapping.emergency.copernicus.eu/activations/{code}/" if code else COPERNICUS_CEMS_ACTIVATIONS,
                    geography=countries or ["GLOBAL"],
                    canonical_facts={
                        "code": code,
                        "category": category,
                        "countries": countries,
                        "activation_time": activation_time.isoformat(),
                        "event_time": item.get("eventTime"),
                        "areas_of_interest": item.get("n_aois"),
                        "products": item.get("n_products"),
                    },
                    raw_metadata={"gdacs_id": item.get("gdacsId"), "centroid": item.get("centroid")},
                    event_time=_parse_dt(item.get("eventTime")) or activation_time,
                    published_at=activation_time,
                    observed_at=datetime.now(timezone.utc),
                ),
            )
            created += int(is_new)
            candidate_id, _ = self._candidate(
                obs.id,
                event_type=event_type,
                title=name,
                geography=countries or ["GLOBAL"],
                facts={
                    "copernicus_activation": code,
                    "category": category,
                    "countries": countries,
                    "official_multilateral_activation": True,
                },
            )
            candidates.append(candidate_id)
        return {"new_observations": created, "candidate_ids": sorted(set(candidates))}
