from datetime import UTC, datetime

import pytest
from app.services.map_query import (
    TripGeometryNotFoundError,
    query_projected_vehicle_positions,
    query_trip_geometry,
)

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class FakeMappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.rows)

    def first(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeSession:
    def __init__(self, results: list[list[dict[str, object]]]) -> None:
        self.results = results

    async def execute(self, statement: object, parameters: object = None) -> FakeResult:
        return FakeResult(self.results.pop(0))


def projected_vehicle_row() -> dict[str, object]:
    return {
        "vehicle_prefix": "001",
        "source_timestamp": NOW,
        "projected_at": NOW,
        "latitude": -15.8,
        "longitude": -48.0,
        "gps_direction": 90.0,
        "speed_kmh": 35.0,
        "low_speed_since": None,
        "current_line": "100",
        "trip_id": "trip-1",
        "route_id": "route-1",
        "route_short_name": "100",
        "route_long_name": "Terminal A / Terminal B",
        "headsign": "Terminal B",
        "direction_id": 0,
        "shape_id": "shape-1",
        "shape_position": 0.5,
        "shape_progress_m": 5000.0,
        "distance_to_shape_m": 4.5,
        "projection_quality": "valid",
        "correlation_level": 1,
        "current_origin_stop_id": "stop-a",
        "current_origin_stop_name": "Parada A",
        "current_destination_stop_id": "stop-b",
        "current_destination_stop_name": "Parada B",
    }


@pytest.mark.asyncio
async def test_projected_vehicle_query_builds_lightweight_map_response() -> None:
    response = await query_projected_vehicle_positions(
        FakeSession([[projected_vehicle_row()]]),  # type: ignore[arg-type]
        generated_at=NOW,
    )

    assert response.count == 1
    assert response.vehicles[0].position_source == "projected"
    assert response.vehicles[0].trip_id == "trip-1"
    assert response.vehicles[0].current_destination_stop_name == "Parada B"


@pytest.mark.asyncio
async def test_trip_geometry_returns_geojson_and_ordered_stops() -> None:
    trip = {
        "feed_id": "feed-1",
        "trip_id": "trip-1",
        "route_id": "route-1",
        "route_short_name": "100",
        "route_long_name": "Terminal A / Terminal B",
        "route_color": "009CDF",
        "route_text_color": "FFFFFF",
        "headsign": "Terminal B",
        "direction_id": 0,
        "shape_id": "shape-1",
        "geometry": '{"type":"LineString","coordinates":[[-48,-15.8],[-47.9,-15.7]]}',
    }
    stop = {
        "stop_id": "stop-a",
        "stop_code": "terminal-a",
        "stop_name": "Terminal A",
        "stop_sequence": 1,
        "latitude": -15.8,
        "longitude": -48.0,
        "shape_position": 0.0,
        "shape_progress_m": 0.0,
        "projection_quality": "valid",
        "arrival_seconds": 3600,
        "departure_seconds": 3600,
    }

    response = await query_trip_geometry(
        FakeSession([[trip], [stop]]),  # type: ignore[arg-type]
        trip_id="trip-1",
    )

    assert response.geometry["type"] == "LineString"
    assert response.shape_id == "shape-1"
    assert response.stops[0].stop_code == "terminal-a"


@pytest.mark.asyncio
async def test_trip_geometry_reports_unknown_trip() -> None:
    with pytest.raises(TripGeometryNotFoundError):
        await query_trip_geometry(
            FakeSession([[]]),  # type: ignore[arg-type]
            trip_id="unknown",
        )
