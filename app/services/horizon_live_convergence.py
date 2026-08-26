from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..horizon_convergence_schemas import HorizonLiveConvergencePollRequest
from ..horizon_event_graph_schemas import HorizonEventGraphBuildRequest
from ..horizon_fuel_schemas import HorizonFuelNormalizeRequest
from ..horizon_live_schemas import HorizonGdeltPollRequest
from ..horizon_models import HorizonGlobalEvent
from ..horizon_provisional_schemas import HorizonProvisionalRefreshRequest
from ..horizon_windy_schemas import HorizonWindyPollRequest
from .horizon_convergence import HorizonConvergenceService
from .horizon_event_graph import HorizonEventGraphService
from .horizon_fuel import HorizonFuelService
from .horizon_gdacs import HorizonGdacsService
from .horizon_global_alert_normalizer import HorizonGlobalAlertNormalizer
from .horizon_live import HorizonLiveService
from .horizon_meteoalarm import HorizonMeteoAlarmService
from .horizon_meteofrance import HorizonMeteoFranceService
from .horizon_normalizer import HorizonMeteoFranceNormalizer
from .horizon_provisional import HorizonProvisionalService
from .horizon_rte_realtime import HorizonRteRealtimeService
from .horizon_sncf import HorizonSncfService
from .horizon_vigicrues import HorizonVigicruesService
from .horizon_weather_chain import HorizonWeatherChainService
from .horizon_windy import HorizonWindyService
from .horizon_world_observers import HorizonWorldObserverService
from .horizon_world_pulse import HorizonWorldPulseService


class HorizonLiveConvergenceService:
    ENGINE_VERSION = "horizon-live-convergence-fabric-v0.5-world-observers"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _safe_call(name: str, fn) -> dict:
        try:
            return {"source": name, "ok": True, "result": fn()}
        except Exception as exc:
            return {"source": name, "ok": False, "error": str(exc)[:500]}

    def poll(self, request: HorizonLiveConvergencePollRequest) -> dict:
        now = datetime.now(timezone.utc)
        results: list[dict] = []

        if request.include_gdelt:
            results.append(self._safe_call(
                "gdelt-doc-2",
                lambda: HorizonLiveService(self.db).poll_gdelt(HorizonGdeltPollRequest()),
            ))

        if request.include_gdacs:
            def poll_gdacs():
                raw = HorizonGdacsService(self.db).poll(request.gdacs)
                normalized = HorizonGlobalAlertNormalizer(self.db).normalize_latest_gdacs(
                    max_observations=min(5000, request.gdacs.page_size * request.gdacs.max_pages)
                )
                return {"poll": raw, "normalize": normalized}
            results.append(self._safe_call("gdacs-official", poll_gdacs))

        if request.include_meteofrance:
            if settings.meteofrance_application_id:
                def poll_meteo():
                    raw = HorizonMeteoFranceService(self.db).poll(settings.meteofrance_application_id)
                    normalized = HorizonMeteoFranceNormalizer(self.db).normalize_latest()
                    return {"poll": raw, "normalize": normalized}
                results.append(self._safe_call("meteofrance-vigilance", poll_meteo))
            else:
                results.append({
                    "source": "meteofrance-vigilance",
                    "ok": False,
                    "skipped": True,
                    "reason": "METEOFRANCE_APPLICATION_ID is not configured",
                })

        if request.include_meteoalarm:
            def poll_meteoalarm():
                raw = HorizonMeteoAlarmService(self.db).poll(request.meteoalarm)
                normalized = HorizonGlobalAlertNormalizer(self.db).normalize_latest_meteoalarm(
                    max_observations=min(
                        5000,
                        max(1, len(request.meteoalarm.countries)) * request.meteoalarm.max_entries_per_country,
                    )
                )
                return {"poll": raw, "normalize": normalized}
            results.append(self._safe_call("meteoalarm-atom", poll_meteoalarm))

        if request.include_fuel:
            def poll_fuel():
                raw = HorizonFuelService(self.db).poll()
                normalized = HorizonFuelService(self.db).normalize_latest(HorizonFuelNormalizeRequest())
                return {"poll": raw, "normalize": normalized}
            results.append(self._safe_call("fr-fuel-ruptures-live", poll_fuel))

        if request.include_rte_realtime:
            results.append(self._safe_call(
                "rte-eco2mix-regional-tr",
                lambda: HorizonRteRealtimeService(self.db).poll(request.rte),
            ))

        if request.include_vigicrues:
            results.append(self._safe_call(
                "vigicrues-official",
                lambda: HorizonVigicruesService(self.db).poll(request.vigicrues),
            ))

        if request.include_sncf:
            results.append(self._safe_call(
                "sncf-service-alerts",
                lambda: HorizonSncfService(self.db).poll(request.sncf),
            ))

        if request.include_world_pulse:
            results.append(self._safe_call(
                "world-pulse",
                lambda: HorizonWorldPulseService(self.db).poll(fred_api_key=settings.fred_api_key),
            ))
            results.append(self._safe_call(
                "world-observers",
                lambda: HorizonWorldObserverService(self.db).poll(),
            ))

        if request.windy_points:
            if settings.windy_point_forecast_api_key:
                for index, point in enumerate(request.windy_points):
                    windy_request = HorizonWindyPollRequest(
                        lat=point.lat,
                        lon=point.lon,
                        geography=point.geography or ["FR"],
                        heat_watch_threshold_c=point.heat_watch_threshold_c,
                    )
                    results.append(self._safe_call(
                        f"windy-point-forecast:{index}",
                        lambda windy_request=windy_request: HorizonWindyService(self.db).poll(
                            windy_request,
                            settings.windy_point_forecast_api_key,
                        ),
                    ))
            else:
                results.append({
                    "source": "windy-point-forecast",
                    "ok": False,
                    "skipped": True,
                    "reason": "WINDY_POINT_FORECAST_API_KEY is not configured",
                })

        provisional = None
        if request.refresh_provisional_candidates:
            provisional = self._safe_call(
                "provisional-candidate-refresh",
                lambda: HorizonProvisionalService(self.db).refresh(
                    HorizonProvisionalRefreshRequest(max_candidates=3000)
                ),
            )

        weather_chain = self._safe_call(
            "weather-chain-reconciliation",
            lambda: HorizonWeatherChainService(self.db).reconcile(max_forecasts=5000, max_chains=5000),
        )

        snapshots: list[dict] = []
        snapshot_errors: list[dict] = []
        if request.snapshot_recent_active_events:
            cutoff = now.replace(tzinfo=None) - timedelta(days=14)
            active_events = (
                self.db.query(HorizonGlobalEvent)
                .filter(
                    HorizonGlobalEvent.status == "active",
                    HorizonGlobalEvent.first_observed_at >= cutoff,
                )
                .order_by(HorizonGlobalEvent.first_observed_at.desc(), HorizonGlobalEvent.id.desc())
                .limit(request.max_active_events)
                .all()
            )
            convergence = HorizonConvergenceService(self.db)
            for event in active_events:
                try:
                    snapshots.append(convergence.build_snapshot(event.id, as_of=now))
                except ValueError as exc:
                    snapshot_errors.append({"event_id": event.id, "error": str(exc)[:300]})

        event_graph = None
        if request.build_event_graph:
            event_graph = self._safe_call(
                "cross-source-event-graph",
                lambda: HorizonEventGraphService(self.db).build(
                    HorizonEventGraphBuildRequest(
                        as_of=now,
                        lookback_hours=request.event_graph_lookback_hours,
                        max_events=1000,
                        max_candidates=1200,
                        max_signals=4000,
                    )
                ),
            )

        successful = sum(1 for item in results if item.get("ok") is True)
        failed = sum(1 for item in results if item.get("ok") is False and not item.get("skipped"))
        skipped = sum(1 for item in results if item.get("skipped"))
        return {
            "engine": self.ENGINE_VERSION,
            "observed_at": now.isoformat(),
            "sources": results,
            "sources_succeeded": successful,
            "sources_failed": failed,
            "sources_skipped_for_configuration": skipped,
            "provisional_refresh": provisional,
            "weather_chain": weather_chain,
            "convergence_snapshots": snapshots,
            "convergence_snapshot_errors": snapshot_errors,
            "event_graph": event_graph,
            "capability_matrix": HorizonConvergenceService.capability_matrix(),
            "critical_semantics": {
                "source_failure_isolated": True,
                "source_count_is_not_truth_vote": True,
                "aggregators_can_share_independence_family_with_origin": True,
                "gdacs_adapter_directly_confirms_event": False,
                "meteoalarm_adapter_directly_confirms_event": False,
                "eonet_adapter_directly_confirms_event": False,
                "convergence_score_is_probability": False,
                "event_graph_dependency_is_causal_proof": False,
                "gated_sources_are_not_faked": True,
                "world_pulse_enabled": True,
                "who_outbreak_observer_enabled": True,
                "nasa_eonet_observer_enabled": True,
                "numeric_probabilities_enabled": False,
            },
        }
