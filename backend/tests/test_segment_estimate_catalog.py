from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.segment_aggregation import (
    EstimateCandidate,
    LiveEstimateCandidate,
    historical_profile_slots,
    metric_identities_for_segment,
)
from app.services.segment_estimate_catalog import SegmentEstimateCatalog
from app.services.vehicle_eta import RemainingTripSegment

NOW = datetime(2026, 8, 29, 13, 2, tzinfo=UTC)
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
SEGMENT = RemainingTripSegment("A", "B", 1, 2, 1.0)


def empty_catalog(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "live_by_key": {},
        "profiles_by_key_and_slot": {},
        "planned_by_scope_pair_and_slot": {},
    }
    values.update(overrides)
    return SegmentEstimateCatalog(**values)


def test_catalog_prefers_recent_live_metric() -> None:
    physical, _ = metric_identities_for_segment(
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="route",
        direction_id=0,
    )
    catalog = empty_catalog(
        live_by_key={
            physical.metric_key: LiveEstimateCandidate(
                value_seconds=75,
                reliability=0.8,
                sample_count=6,
                window_end=NOW - timedelta(minutes=5),
            )
        }
    )

    result = catalog.resolve(
        SEGMENT, NOW, "physical", route_id="route", direction_id=0
    )

    assert result.source == "live"
    assert result.value_seconds == 75
    assert result.age_seconds == 300


def test_catalog_uses_nearest_historical_slot_after_live_expires() -> None:
    physical, _ = metric_identities_for_segment(
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="route",
        direction_id=0,
    )
    slots = {
        offset: (day_type, slot_index)
        for day_type, slot_index, offset in historical_profile_slots(NOW)
    }
    catalog = empty_catalog(
        live_by_key={
            physical.metric_key: LiveEstimateCandidate(
                value_seconds=75,
                reliability=0.8,
                sample_count=6,
                window_end=NOW - timedelta(hours=2),
            )
        },
        profiles_by_key_and_slot={
            (physical.metric_key, *slots[-5]): EstimateCandidate(90, 0.7, 8),
            (physical.metric_key, *slots[5]): EstimateCandidate(110, 0.6, 7),
        },
    )

    result = catalog.resolve(
        SEGMENT, NOW, "physical", route_id="route", direction_id=0
    )

    assert result.source == "historical"
    assert result.value_seconds == 90
    assert result.historical_offset_minutes == -5


def test_catalog_uses_first_planned_slot_with_equal_trip_weight() -> None:
    local_window = NOW.astimezone(LOCAL_TIMEZONE).replace(
        minute=10,
        second=0,
        microsecond=0,
    )
    catalog = empty_catalog(
        planned_by_scope_pair_and_slot={
            (
                "service",
                "A",
                "B",
                "route",
                0,
                local_window.date(),
                (local_window.hour * 60 + local_window.minute) // 5,
            ): EstimateCandidate(90, 1, 2)
        }
    )

    result = catalog.resolve(
        SEGMENT, NOW, "service", route_id="route", direction_id=0
    )

    assert result.source == "gtfs_planned"
    assert result.value_seconds == 90
    assert result.reliability == 1
    assert result.sample_count == 2
