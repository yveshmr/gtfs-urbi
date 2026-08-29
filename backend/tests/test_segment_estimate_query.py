from datetime import UTC, datetime, timedelta

import pytest
from app.services.segment_aggregation import metric_identities_for_segment, profile_slot
from app.services.segment_estimate_query import query_segment_estimates


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self.rows


class FakeSession:
    def __init__(self, results: list[list[dict[str, object]]]) -> None:
        self.results = results
        self.executed: list[tuple[object, object]] = []

    async def execute(self, statement: object, parameters: object) -> FakeResult:
        self.executed.append((statement, parameters))
        return FakeResult(self.results.pop(0))


@pytest.mark.asyncio
async def test_query_returns_physical_and_service_live_estimates() -> None:
    queried_at = datetime(2026, 8, 29, 13, 2, tzinfo=UTC)
    physical, service = metric_identities_for_segment(
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="R1",
        direction_id=1,
    )
    session = FakeSession(
        [
            [
                {
                    "metric_key": physical.metric_key,
                    "mean_seconds": 100.0,
                    "reliability": 0.6,
                    "sample_count_accepted": 3,
                    "window_end": queried_at,
                },
                {
                    "metric_key": service.metric_key,
                    "mean_seconds": 110.0,
                    "reliability": 0.4,
                    "sample_count_accepted": 2,
                    "window_end": queried_at,
                },
            ],
            [],
        ]
    )

    result = await query_segment_estimates(
        session,  # type: ignore[arg-type]
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="R1",
        direction_id=1,
        queried_at=queried_at,
    )

    assert result.physical.source == "live"
    assert result.physical.value_seconds == 100
    assert result.service is not None
    assert result.service.source == "live"
    assert result.service.value_seconds == 110


@pytest.mark.asyncio
async def test_query_falls_back_to_nearest_historical_slot() -> None:
    queried_at = datetime(2026, 8, 29, 13, 7, tzinfo=UTC)
    physical, _ = metric_identities_for_segment(
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="R1",
        direction_id=1,
    )
    day_type, exact_slot = profile_slot(queried_at)
    session = FakeSession(
        [
            [
                {
                    "metric_key": physical.metric_key,
                    "mean_seconds": 90.0,
                    "reliability": 0.8,
                    "sample_count_accepted": 8,
                    "window_end": queried_at - timedelta(hours=1, seconds=1),
                }
            ],
            [
                {
                    "metric_key": physical.metric_key,
                    "day_type": day_type,
                    "slot_index": exact_slot + 1,
                    "mean_seconds": 120.0,
                    "reliability": 0.5,
                    "sample_count_accepted": 5,
                }
            ],
        ]
    )

    result = await query_segment_estimates(
        session,  # type: ignore[arg-type]
        origin_stop_id="A",
        destination_stop_id="B",
        queried_at=queried_at,
    )

    assert result.physical.source == "historical"
    assert result.physical.value_seconds == 120
    assert result.physical.historical_offset_minutes == 5
    assert result.service is None


@pytest.mark.asyncio
async def test_query_requires_route_and_direction_together() -> None:
    with pytest.raises(ValueError, match="provided together"):
        await query_segment_estimates(
            FakeSession([]),  # type: ignore[arg-type]
            origin_stop_id="A",
            destination_stop_id="B",
            route_id="R1",
            queried_at=datetime(2026, 8, 29, 13, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_query_uses_equally_weighted_gtfs_trips_at_first_available_slot() -> None:
    queried_at = datetime(2026, 8, 29, 13, 7, tzinfo=UTC)
    session = FakeSession(
        [
            [],
            [],
            [
                {
                    "route_id": "R1",
                    "direction_id": 0,
                    "offset_minutes": -5,
                    "duration_seconds": 100,
                },
                {
                    "route_id": "R2",
                    "direction_id": 1,
                    "offset_minutes": -5,
                    "duration_seconds": 140,
                },
                {
                    "route_id": "R3",
                    "direction_id": 0,
                    "offset_minutes": 5,
                    "duration_seconds": 300,
                },
            ],
        ]
    )

    result = await query_segment_estimates(
        session,  # type: ignore[arg-type]
        origin_stop_id="A",
        destination_stop_id="B",
        queried_at=queried_at,
    )

    assert result.physical.source == "gtfs_planned"
    assert result.physical.value_seconds == 120
    assert result.physical.reliability == 1
    assert result.physical.sample_count == 2


@pytest.mark.asyncio
async def test_query_stays_unavailable_without_gtfs_within_thirty_minutes() -> None:
    session = FakeSession([[], [], []])

    result = await query_segment_estimates(
        session,  # type: ignore[arg-type]
        origin_stop_id="A",
        destination_stop_id="B",
        queried_at=datetime(2026, 8, 29, 13, tzinfo=UTC),
    )

    assert result.physical.source == "unavailable"
