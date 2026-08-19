from datetime import datetime
from uuid import uuid4

from app.db import SessionLocal
from app.horizon_models import HorizonGlobalEvent
from app.horizon_source_schemas import HorizonSourceUpsert
from app.services.horizon_coverage import HorizonHistoricalCoverageService
from app.services.horizon_sources import HorizonSourceService


def test_complete_signal_coverage_can_be_stitched_but_partial_or_gapped_streams_do_not_count():
    tag = uuid4().hex[:10]
    event_type = f"coverage-event-{tag}"
    signal_type = f"coverage-signal-{tag}"
    partial_type = f"partial-signal-{tag}"
    db = SessionLocal()
    try:
        source = HorizonSourceService(db).upsert_source(
            HorizonSourceUpsert(
                source_key=f"coverage-source-{tag}",
                name=f"Coverage Source {tag}",
                source_class="official_statistical",
                adapter_kind="coverage_fixture",
                domains=["test"],
                geography=["FR"],
                base_locator="https://example.invalid/coverage-fixture",
                trust_weight=0.9,
                refresh_seconds=3600,
                requires_credentials=False,
                enabled=True,
                metadata_json={"test_only": True},
            )
        )
        coverage = HorizonHistoricalCoverageService(db)
        coverage.record_interval(
            source,
            coverage_kind="signal",
            event_types=[event_type],
            signal_types=[signal_type],
            geography=["FR"],
            start_at=datetime.fromisoformat("2020-01-01T00:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T05:00:00"),
            completeness="complete",
            basis="fixture_first_half",
        )
        coverage.record_interval(
            source,
            coverage_kind="signal",
            event_types=[event_type],
            signal_types=[signal_type],
            geography=["FR"],
            start_at=datetime.fromisoformat("2020-01-01T05:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T10:00:00"),
            completeness="complete",
            basis="fixture_second_half",
        )
        coverage.record_interval(
            source,
            coverage_kind="signal",
            event_types=[event_type],
            signal_types=[partial_type],
            geography=["FR"],
            start_at=datetime.fromisoformat("2020-01-01T00:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T10:00:00"),
            completeness="partial",
            basis="fixture_partial_stream",
        )

        event = HorizonGlobalEvent(event_type=event_type, geography=["FR"])
        full = coverage.signal_coverage(
            event,
            {signal_type},
            start_at=datetime.fromisoformat("2020-01-01T00:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T10:00:00"),
        )
        assert full["complete"] is True
        assert full["covered_signal_types"] == [signal_type]
        assert full["missing_signal_types"] == []
        assert full["negative_label_authorized"] is True

        missing_partial = coverage.signal_coverage(
            event,
            {signal_type, partial_type},
            start_at=datetime.fromisoformat("2020-01-01T00:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T10:00:00"),
        )
        assert missing_partial["complete"] is False
        assert partial_type in missing_partial["missing_signal_types"]
        assert missing_partial["negative_label_authorized"] is False
        assert missing_partial["absence_of_signal_without_coverage_means_non_occurrence"] is False

        gapped = coverage.signal_coverage(
            event,
            {signal_type},
            start_at=datetime.fromisoformat("2019-12-31T23:00:00"),
            end_at=datetime.fromisoformat("2020-01-01T10:00:00"),
        )
        assert gapped["complete"] is False
        assert gapped["negative_label_authorized"] is False
    finally:
        db.close()
