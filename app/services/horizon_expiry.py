from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..horizon_expiry_models import HorizonForecastExpiry
from ..horizon_expiry_schemas import HorizonForecastExpiryScanRequest
from ..horizon_materialization_schemas import HorizonMaterializationScanRequest
from ..horizon_models import HorizonBehaviorPattern, HorizonForecast, HorizonForecastResolution
from .horizon_materialization import HorizonMaterializationService
from .policy import sha256_dict


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class HorizonForecastExpiryService:
    ENGINE_VERSION = "horizon-forecast-expiry-v0.1"

    def __init__(self, db: Session):
        self.db = db

    def scan(self, request: HorizonForecastExpiryScanRequest) -> dict:
        cutoff = _utc_naive(request.as_of) if request.as_of else datetime.utcnow()

        # First give every still-open forecast a fair chance to resolve positively.
        HorizonMaterializationService(self.db).scan(
            HorizonMaterializationScanRequest(
                mode=request.mode,
                as_of=cutoff,
                max_forecasts=request.max_forecasts,
                forecast_ids=request.forecast_ids,
            )
        )

        query = self.db.query(HorizonForecast).filter(HorizonForecast.status == "open")
        if request.mode != "all":
            query = query.filter(HorizonForecast.mode == request.mode)
        if request.forecast_ids:
            query = query.filter(HorizonForecast.id.in_(set(request.forecast_ids)))
        forecasts = (
            query.order_by(HorizonForecast.as_of.asc(), HorizonForecast.id.asc())
            .limit(request.max_forecasts)
            .all()
        )

        expired_ids: list[int] = []
        still_open_ids: list[int] = []
        no_deadline_ids: list[int] = []
        no_materialization_rule_ids: list[int] = []

        for forecast in forecasts:
            if forecast.expected_onset_high is None:
                no_deadline_ids.append(forecast.id)
                continue
            pattern = (
                self.db.query(HorizonBehaviorPattern)
                .filter(HorizonBehaviorPattern.id == forecast.pattern_id)
                .one_or_none()
            )
            if pattern is None:
                still_open_ids.append(forecast.id)
                continue

            signal_types = HorizonMaterializationService.materialization_signal_types_for_pattern(pattern)
            if not signal_types:
                no_materialization_rule_ids.append(forecast.id)
                continue

            grace_hours = HorizonMaterializationService.grace_hours_for_pattern(pattern)
            deadline = forecast.expected_onset_high + timedelta(hours=grace_hours)
            if cutoff <= deadline:
                still_open_ids.append(forecast.id)
                continue

            existing_resolution = (
                self.db.query(HorizonForecastResolution)
                .filter(HorizonForecastResolution.forecast_id == forecast.id)
                .one_or_none()
            )
            if existing_resolution is not None:
                continue

            expiry_key = sha256_dict(
                {
                    "engine": self.ENGINE_VERSION,
                    "forecast_id": forecast.id,
                    "expected_onset_high": forecast.expected_onset_high.isoformat(),
                    "grace_hours": grace_hours,
                    "deadline": deadline.isoformat(),
                }
            )
            expiry = HorizonForecastExpiry(
                expiry_key=expiry_key,
                forecast_id=forecast.id,
                event_id=forecast.event_id,
                pattern_id=forecast.pattern_id,
                expected_onset_high=forecast.expected_onset_high,
                grace_hours=grace_hours,
                expiry_deadline=deadline,
                expired_at=cutoff,
                checked_materialization_signal_types=sorted(signal_types),
                rule_snapshot={
                    "engine": self.ENGINE_VERSION,
                    "basis": "forecast exceeded expected_onset_high plus grace without admissible materialization",
                    "grace_hours": grace_hours,
                    "materialization_signal_types": sorted(signal_types),
                    "late_occurrence_counts_as_success": False,
                    "probability": False,
                    "causal_proof": False,
                },
            )
            resolution = HorizonForecastResolution(
                forecast_id=forecast.id,
                outcome_occurred=False,
                outcome_summary="Predicted observable outcome did not materialize within its declared validity window.",
                correctness="false",
                became_obvious_at=None,
                personal_action_at=None,
                predictive_lead_time_hours=None,
                actionable_lead_time_hours=None,
                notes=(
                    "Automatically expired by HORIZON. A later occurrence does not retroactively convert "
                    "this time-bounded forecast into a success."
                ),
            )
            self.db.add(expiry)
            self.db.add(resolution)
            forecast.status = "resolved"
            forecast.calibration_status = "labeled"
            self.db.flush()
            expired_ids.append(forecast.id)

        self.db.commit()
        return {
            "engine": self.ENGINE_VERSION,
            "mode": request.mode,
            "as_of": cutoff.isoformat(),
            "scanned_open_after_materialization": len(forecasts),
            "expired": len(expired_ids),
            "expired_forecast_ids": expired_ids,
            "still_open_forecast_ids": still_open_ids,
            "no_deadline_forecast_ids": no_deadline_ids,
            "no_materialization_rule_forecast_ids": no_materialization_rule_ids,
            "late_occurrence_counts_as_success": False,
        }

    def list_expiries(self, limit: int = 100) -> list[HorizonForecastExpiry]:
        return (
            self.db.query(HorizonForecastExpiry)
            .order_by(HorizonForecastExpiry.expired_at.desc(), HorizonForecastExpiry.id.desc())
            .limit(limit)
            .all()
        )
