from datetime import UTC, datetime

import app.services.vehicle_eta_query as eta_query_module
import pytest
from app.services.segment_aggregation import ResolvedSegmentEstimate
from app.services.vehicle_eta_query import (
    VehicleEtaUnavailableError,
    query_vehicle_eta,
)

NOW = datetime(2026, 8, 29, 13, tzinfo=UTC)


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self.rows


class FakeSession:
    def __init__(self, results: list[list[dict[str, object]]]) -> None:
        self.results = results

    async def execute(self, statement: object, parameters: object) -> FakeResult:
        return FakeResult(self.results.pop(0))


class FakeCatalog:
    def resolve(self, segment, estimate_at, scope):  # type: ignore[no-untyped-def]
        if scope == "physical":
            return ResolvedSegmentEstimate(100, 0.8, 4, "live", 0, None)
        return ResolvedSegmentEstimate(120, 1, 2, "gtfs_planned", None, None)


def state_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "vehicle_prefix": "001",
        "source_timestamp": NOW,
        "feed_id": "feed",
        "trip_id": "trip",
        "route_id": "route",
        "direction_id": 0,
        "shape_progress_m": 150.0,
        "current_origin_stop_sequence": 1,
        "current_destination_stop_sequence": 2,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_vehicle_eta_returns_current_and_future_trip_end_scenarios(
    monkeypatch,
) -> None:
    stops = [
        {
            "stop_id": "A",
            "stop_sequence": 1,
            "shape_progress_m": 100.0,
            "arrival_seconds": 0,
            "departure_seconds": 0,
        },
        {
            "stop_id": "B",
            "stop_sequence": 2,
            "shape_progress_m": 200.0,
            "arrival_seconds": 100,
            "departure_seconds": 100,
        },
        {
            "stop_id": "C",
            "stop_sequence": 3,
            "shape_progress_m": 300.0,
            "arrival_seconds": 200,
            "departure_seconds": 200,
        },
    ]

    async def load_catalog(session, **kwargs):  # type: ignore[no-untyped-def]
        return FakeCatalog()

    monkeypatch.setattr(
        eta_query_module,
        "load_segment_estimate_catalog",
        load_catalog,
    )
    result = await query_vehicle_eta(
        FakeSession([[state_row()], stops]),  # type: ignore[arg-type]
        vehicle_prefix="001",
        queried_at=NOW,
    )

    assert result.next_stop_id == "B"
    assert result.terminal_stop_id == "C"
    assert result.remaining_segment_count == 2
    assert result.current_time_physical.next_stop.value_seconds == 50
    assert result.current_time_physical.trip_end.value_seconds == 150
    assert result.future_time_service.next_stop.value_seconds == 60
    assert result.future_time_service.trip_end.value_seconds == 180


@pytest.mark.asyncio
async def test_vehicle_eta_rejects_position_older_than_five_minutes() -> None:
    with pytest.raises(VehicleEtaUnavailableError, match="older than five minutes"):
        await query_vehicle_eta(
            FakeSession([[state_row(source_timestamp=NOW.replace(hour=12, minute=54))]]),  # type: ignore[arg-type]
            vehicle_prefix="001",
            queried_at=NOW,
        )
