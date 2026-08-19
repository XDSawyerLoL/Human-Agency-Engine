from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .horizon_global_alert_schemas import HorizonGdacsPollRequest, HorizonMeteoAlarmPollRequest


class HorizonRteRealtimePollRequest(BaseModel):
    region_codes: list[str] = Field(default_factory=list, max_length=13)
    baseline_days: int = Field(default=7, ge=3, le=14)
    rolling_points: int = Field(default=8, ge=4, le=16)
    minimum_lift_ratio: float = Field(default=0.03, ge=0.0, le=0.50)
    max_records_per_region: int = Field(default=1000, ge=100, le=5000)

    @model_validator(mode="after")
    def normalize_regions(self):
        self.region_codes = sorted({str(item).strip() for item in self.region_codes if str(item).strip()})
        return self


class HorizonVigicruesPollRequest(BaseModel):
    minimum_level: int = Field(default=2, ge=2, le=4)
    max_features: int = Field(default=1000, ge=1, le=5000)


class HorizonSncfPollRequest(BaseModel):
    max_situations: int = Field(default=250, ge=1, le=2000)


class HorizonConvergenceSnapshotRequest(BaseModel):
    as_of: datetime | None = None


class HorizonWindyPoint(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    geography: list[str] = Field(default_factory=list)
    heat_watch_threshold_c: float = Field(default=32.0, ge=20.0, le=55.0)


class HorizonLiveConvergencePollRequest(BaseModel):
    include_gdelt: bool = True
    include_gdacs: bool = True
    include_meteofrance: bool = True
    include_meteoalarm: bool = True
    include_fuel: bool = True
    include_rte_realtime: bool = True
    include_vigicrues: bool = True
    include_sncf: bool = True
    windy_points: list[HorizonWindyPoint] = Field(default_factory=list, max_length=20)
    refresh_provisional_candidates: bool = True
    snapshot_recent_active_events: bool = True
    max_active_events: int = Field(default=100, ge=1, le=1000)
    build_event_graph: bool = True
    event_graph_lookback_hours: int = Field(default=336, ge=24, le=24 * 30)
    gdacs: HorizonGdacsPollRequest = Field(default_factory=HorizonGdacsPollRequest)
    meteoalarm: HorizonMeteoAlarmPollRequest = Field(default_factory=HorizonMeteoAlarmPollRequest)
    rte: HorizonRteRealtimePollRequest = Field(default_factory=HorizonRteRealtimePollRequest)
    vigicrues: HorizonVigicruesPollRequest = Field(default_factory=HorizonVigicruesPollRequest)
    sncf: HorizonSncfPollRequest = Field(default_factory=HorizonSncfPollRequest)
