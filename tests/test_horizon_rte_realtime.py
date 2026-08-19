from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from app.db import SessionLocal
from app.horizon_convergence_schemas import HorizonRteRealtimePollRequest
from app.horizon_models import HorizonGlobalEvent, HorizonSocialSignal
from app.services.horizon_rte_realtime import HorizonRteRealtimeService, RTE_REALTIME_ENDPOINT


def _records() -> list[dict]:
    rows = []
    start = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    for day_offset in range(8):
        day = start + timedelta(days=day_offset)
        value = 1100 if day_offset == 7 else 1000
        for point in range(8):
            at = day + timedelta(minutes=15 * point)
            rows.append({
                "code_insee_region": "11",
                "libelle_region": "Île-de-France",
                "date_heure": at.isoformat().replace("+00:00", "Z"),
                "consommation": value,
                "nature": "Données temps réel",
            })
    return rows


def test_rte_realtime_creates_live_proxy_but_never_final_materialization_label():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    event = HorizonGlobalEvent(
        event_key=f"rte-live-region-{tag}",
        event_type="extreme_heat_region",
        title="Synthetic live regional heat",
        summary="fixture",
        geography=["FR", "REGION:11"],
        source="meteofrance-vigilance",
        source_url="https://vigilance.meteofrance.fr/fr",
        source_reliability=0.97,
        raw_facts={"region_code": "11", "departments": ["75", "92"]},
        occurred_at=datetime(2026, 8, 10, 8, 0),
        first_observed_at=datetime(2026, 8, 10, 8, 0),
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    records = _records()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(RTE_REALTIME_ENDPOINT)
        return httpx.Response(200, json={"results": records, "total_count": len(records)}, request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    request = HorizonRteRealtimePollRequest(
        region_codes=["11"],
        baseline_days=7,
        rolling_points=8,
        minimum_lift_ratio=0.03,
        max_records_per_region=1000,
    )
    observed_at = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    try:
        result = HorizonRteRealtimeService(db).poll(request, client=mock, observed_at=observed_at)
        assert result["new_observations"] == 1
        assert result["critical_semantics"]["realtime_signal_is_final_materialization_label"] is False
        assert result["critical_semantics"]["signal_authorizes_negative_backtest_label"] is False
        region = next(item for item in result["regions"] if item["region_code"] == "11")
        assert region["above_threshold"] is True
        assert region["lift_ratio"] > 0.09

        signal = db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id == event.id,
            HorizonSocialSignal.signal_type == "cooling_load_pressure_live",
        ).one()
        assert signal.reliability == 0.82
        assert signal.evidence["final_materialization_label"] is False
        assert signal.evidence["cooling_causality_proven"] is False

        replay = HorizonRteRealtimeService(db).poll(request, client=mock, observed_at=observed_at)
        assert replay["new_observations"] == 0
        assert db.query(HorizonSocialSignal).filter(
            HorizonSocialSignal.event_id == event.id,
            HorizonSocialSignal.signal_type == "cooling_load_pressure_live",
        ).count() == 1
    finally:
        mock.close()
        db.close()
