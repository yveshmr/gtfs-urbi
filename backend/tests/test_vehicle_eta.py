from datetime import UTC, datetime

import pytest
from app.services.segment_aggregation import ResolvedSegmentEstimate
from app.services.vehicle_eta import RemainingTripSegment, compose_eta_projection

NOW = datetime(2026, 8, 29, 13, tzinfo=UTC)


@pytest.mark.asyncio
async def test_eta_prorates_current_segment_and_sums_until_trip_end() -> None:
    calls: list[datetime] = []

    async def resolver(segment, estimate_at, scope):  # type: ignore[no-untyped-def]
        calls.append(estimate_at)
        return ResolvedSegmentEstimate(100, 0.8, 4, "live", 0, None)

    result = await compose_eta_projection(
        segments=(
            RemainingTripSegment("A", "B", 1, 2, 0.25),
            RemainingTripSegment("B", "C", 2, 3),
        ),
        queried_at=NOW,
        scope="physical",
        scenario="future_time",
        resolver=resolver,
    )

    assert result.next_stop.value_seconds == 25
    assert result.trip_end.value_seconds == 125
    assert result.trip_end.reliability == pytest.approx(0.8)
    assert result.trip_end.source_counts == {"live": 2}
    assert calls == [NOW, NOW.replace(second=25)]


@pytest.mark.asyncio
async def test_current_time_scenario_uses_same_timestamp_for_every_segment() -> None:
    calls: list[datetime] = []

    async def resolver(segment, estimate_at, scope):  # type: ignore[no-untyped-def]
        calls.append(estimate_at)
        return ResolvedSegmentEstimate(60, 1, 1, "gtfs_planned", None, None)

    result = await compose_eta_projection(
        segments=(
            RemainingTripSegment("A", "B", 1, 2),
            RemainingTripSegment("B", "C", 2, 3),
            RemainingTripSegment("C", "D", 3, 4),
        ),
        queried_at=NOW,
        scope="service",
        scenario="current_time",
        resolver=resolver,
    )

    assert result.trip_end.value_seconds == 180
    assert calls == [NOW, NOW, NOW]


@pytest.mark.asyncio
async def test_missing_segment_keeps_next_eta_but_marks_trip_end_incomplete() -> None:
    async def resolver(segment, estimate_at, scope):  # type: ignore[no-untyped-def]
        if segment.origin_stop_id == "B":
            return ResolvedSegmentEstimate(None, 0, 0, "unavailable", None, None)
        return ResolvedSegmentEstimate(50, 0.5, 1, "historical", None, 0)

    result = await compose_eta_projection(
        segments=(
            RemainingTripSegment("A", "B", 1, 2),
            RemainingTripSegment("B", "C", 2, 3),
        ),
        queried_at=NOW,
        scope="physical",
        scenario="future_time",
        resolver=resolver,
    )

    assert result.next_stop.complete is True
    assert result.trip_end.complete is False
    assert result.trip_end.value_seconds is None
    assert result.trip_end.segments_covered == 1
    assert result.trip_end.missing_origin_stop_id == "B"
