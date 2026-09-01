from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.map import (
    ProjectedVehiclePositionListResponse,
    ProjectedVehiclePositionResponse,
    TripGeometryResponse,
    TripStopGeometryResponse,
)


class TripGeometryNotFoundError(LookupError):
    pass


async def query_projected_vehicle_positions(
    session: AsyncSession,
    *,
    generated_at: datetime,
) -> ProjectedVehiclePositionListResponse:
    if generated_at.tzinfo is None:
        raise ValueError("The map timestamp must include a timezone.")
    result = await session.execute(
        text(
            """
            SELECT
                vehicle.vehicle_prefix,
                vehicle.source_timestamp,
                vehicle.projected_at,
                ST_Y(vehicle.projected_location) AS latitude,
                ST_X(vehicle.projected_location) AS longitude,
                vehicle.gps_direction,
                vehicle.speed_kmh,
                vehicle.low_speed_since,
                vehicle.current_line,
                vehicle.trip_id,
                vehicle.route_id,
                route.short_name AS route_short_name,
                route.long_name AS route_long_name,
                trip.headsign,
                trip.direction_id,
                vehicle.shape_id,
                vehicle.shape_position,
                vehicle.shape_progress_m,
                vehicle.distance_to_shape_m,
                vehicle.projection_quality,
                vehicle.correlation_level,
                vehicle.current_origin_stop_id,
                origin.name AS current_origin_stop_name,
                vehicle.current_destination_stop_id,
                destination.name AS current_destination_stop_name
            FROM realtime.vehicle_current_states AS vehicle
            JOIN core.gtfs_trips AS trip
              ON trip.feed_id = vehicle.feed_id
             AND trip.trip_id = vehicle.trip_id
            JOIN core.gtfs_routes AS route
              ON route.feed_id = trip.feed_id
             AND route.route_id = trip.route_id
            LEFT JOIN core.gtfs_stops AS origin
              ON origin.feed_id = vehicle.feed_id
             AND origin.stop_id = vehicle.current_origin_stop_id
            LEFT JOIN core.gtfs_stops AS destination
              ON destination.feed_id = vehicle.feed_id
             AND destination.stop_id = vehicle.current_destination_stop_id
            WHERE vehicle.map_match_status = 'resolved'
              AND vehicle.projected_location IS NOT NULL
              AND vehicle.projected_at IS NOT NULL
              AND vehicle.projection_quality IN ('valid', 'reduced')
              AND vehicle.source_timestamp IS NOT NULL
              AND vehicle.trip_id IS NOT NULL
              AND vehicle.route_id IS NOT NULL
              AND vehicle.shape_id IS NOT NULL
              AND vehicle.shape_position IS NOT NULL
              AND vehicle.shape_progress_m IS NOT NULL
              AND vehicle.distance_to_shape_m IS NOT NULL
            ORDER BY vehicle.vehicle_prefix
            """
        )
    )
    vehicles = [
        ProjectedVehiclePositionResponse(**dict(row)) for row in result.mappings()
    ]
    return ProjectedVehiclePositionListResponse(
        generated_at=generated_at,
        count=len(vehicles),
        vehicles=vehicles,
    )


def _decode_geometry(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("PostGIS returned an invalid trip geometry.")


async def query_trip_geometry(
    session: AsyncSession,
    *,
    trip_id: str,
) -> TripGeometryResponse:
    trip_result = await session.execute(
        text(
            """
            SELECT
                trip.feed_id,
                trip.trip_id,
                trip.route_id,
                route.short_name AS route_short_name,
                route.long_name AS route_long_name,
                route.color AS route_color,
                route.text_color AS route_text_color,
                trip.headsign,
                trip.direction_id,
                trip.shape_id,
                ST_AsGeoJSON(shape.geometry, 6)::json AS geometry
            FROM core.gtfs_trips AS trip
            JOIN core.gtfs_feeds AS feed
              ON feed.id = trip.feed_id
            JOIN core.gtfs_routes AS route
              ON route.feed_id = trip.feed_id
             AND route.route_id = trip.route_id
            JOIN core.gtfs_shapes AS shape
              ON shape.feed_id = trip.feed_id
             AND shape.shape_id = trip.shape_id
            WHERE trip.trip_id = :trip_id
            ORDER BY feed.retrieved_at DESC
            LIMIT 1
            """
        ),
        {"trip_id": trip_id},
    )
    trip_row = trip_result.mappings().first()
    if trip_row is None:
        raise TripGeometryNotFoundError(trip_id)

    stops_result = await session.execute(
        text(
            """
            SELECT
                stop_time.stop_id,
                stop.code AS stop_code,
                stop.name AS stop_name,
                stop_time.stop_sequence,
                stop.latitude,
                stop.longitude,
                stop_time.shape_position,
                stop_time.shape_progress_m,
                stop_time.shape_projection_quality AS projection_quality,
                stop_time.arrival_seconds,
                stop_time.departure_seconds
            FROM core.gtfs_stop_times AS stop_time
            JOIN core.gtfs_stops AS stop
              ON stop.feed_id = stop_time.feed_id
             AND stop.stop_id = stop_time.stop_id
            WHERE stop_time.feed_id = :feed_id
              AND stop_time.trip_id = :trip_id
            ORDER BY stop_time.stop_sequence
            """
        ),
        {"feed_id": trip_row["feed_id"], "trip_id": trip_row["trip_id"]},
    )
    stops = [TripStopGeometryResponse(**dict(row)) for row in stops_result.mappings()]
    return TripGeometryResponse(
        trip_id=trip_row["trip_id"],
        route_id=trip_row["route_id"],
        route_short_name=trip_row["route_short_name"],
        route_long_name=trip_row["route_long_name"],
        route_color=trip_row["route_color"],
        route_text_color=trip_row["route_text_color"],
        headsign=trip_row["headsign"],
        direction_id=trip_row["direction_id"],
        shape_id=trip_row["shape_id"],
        geometry=_decode_geometry(trip_row["geometry"]),
        stops=stops,
    )
