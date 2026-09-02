from datetime import UTC, date, datetime

import pytest
from app.services.active_trip_index import ActiveTripCandidate, PlannedTripSegment
from app.services.planned_eta_snapshot import _compose_planned_result, _remaining_segments

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def candidate() -> ActiveTripCandidate:
    return ActiveTripCandidate(
        feed_id="feed",
        trip_id="trip",
        route_id="route",
        shape_id="shape",
        direction_id=1,
        planned_segments=(
            PlannedTripSegment("A", "B", 1, 2, 100, 200, 120),
            PlannedTripSegment("B", "C", 2, 3, 200, 300, 180),
        ),
        terminal_stop_id="C",
        terminal_arrival_seconds=12 * 3600,
    )


def test_warmup_segments_locate_the_vehicle_without_database_stop_lookup() -> None:
    segments = _remaining_segments(
        candidate(),
        shape_progress_m=150,
        origin_stop_sequence=None,
        destination_stop_sequence=None,
    )

    assert len(segments) == 2
    assert segments[0].remaining_fraction == pytest.approx(0.5)
    assert segments[0].planned_duration_seconds == 120
    assert segments[1].remaining_fraction == 1


@pytest.mark.asyncio
async def test_planned_baseline_is_complete_and_comparable() -> None:
    result = await _compose_planned_result(
        state={
            "vehicle_prefix": "001",
            "shape_progress_m": 150,
            "current_origin_stop_sequence": 1,
            "current_destination_stop_sequence": 2,
        },
        candidate=candidate(),
        queried_at=NOW,
    )

    assert result is not None
    assert result.future_time_service.trip_end.complete is True
    assert result.future_time_service.trip_end.value_seconds == 240
    assert result.future_time_service.trip_end.source_counts == {"gtfs_planned": 2}
    assert result.planned_trip_end_at is not None
    assert result.planned_trip_end_at.date() == date(2026, 9, 2)


@pytest.mark.asyncio
async def test_vehicle_at_terminal_has_zero_planned_eta() -> None:
    result = await _compose_planned_result(
        state={
            "vehicle_prefix": "001",
            "shape_progress_m": 300,
            "current_origin_stop_sequence": None,
            "current_destination_stop_sequence": None,
        },
        candidate=candidate(),
        queried_at=NOW,
    )

    assert result is not None
    assert result.remaining_segment_count == 0
    assert result.future_time_service.trip_end.value_seconds == 0
    assert result.future_time_service.trip_end.estimated_at == NOW


@pytest.mark.asyncio
async def test_circular_trip_uses_the_warmed_full_shape_segment() -> None:
    circular = ActiveTripCandidate(
        feed_id="feed",
        trip_id="circle",
        route_id="route",
        shape_id="shape",
        direction_id=0,
        planned_segments=(
            PlannedTripSegment("T", "T", 1, 2, 1, 20_001, 4_500),
        ),
        terminal_stop_id="T",
        terminal_arrival_seconds=34_620,
        shape_total_distance_m=20_001,
    )

    result = await _compose_planned_result(
        state={
            "vehicle_prefix": "001",
            "shape_progress_m": 19_001,
            "current_origin_stop_sequence": None,
            "current_destination_stop_sequence": None,
        },
        candidate=circular,
        queried_at=NOW,
    )

    assert result is not None
    assert result.future_time_service.trip_end.complete is True
    assert result.future_time_service.trip_end.value_seconds == pytest.approx(225)
