from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.map import SegmentSpeedMapItem, SegmentSpeedMapResponse
from app.services.segment_aggregation import (
    historical_retention_start,
    operational_service_date,
    profile_slot,
)

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_CACHE_TTL = timedelta(seconds=60)
_cache: SegmentSpeedMapResponse | None = None
_cache_lock = asyncio.Lock()


def _decode_geometry(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return decoded
    raise ValueError("PostGIS returned an invalid segment geometry.")


async def query_segment_speed_map(
    session: AsyncSession,
    *,
    generated_at: datetime,
) -> SegmentSpeedMapResponse:
    global _cache
    if _cache is not None and generated_at - _cache.generated_at < _CACHE_TTL:
        return _cache
    async with _cache_lock:
        if _cache is not None and generated_at - _cache.generated_at < _CACHE_TTL:
            return _cache
        _cache = await _query_segment_speed_map_uncached(
            session,
            generated_at=generated_at,
        )
        return _cache


async def _query_segment_speed_map_uncached(
    session: AsyncSession,
    *,
    generated_at: datetime,
) -> SegmentSpeedMapResponse:
    if generated_at.tzinfo is None:
        raise ValueError("The map timestamp must include a timezone.")

    service_date = operational_service_date(generated_at)
    day_type, slot_index = profile_slot(generated_at)
    result = await session.execute(
        text(
            """
            WITH active_traversals AS MATERIALIZED (
                SELECT DISTINCT
                    origin.stop_id AS origin_stop_id,
                    destination.stop_id AS destination_stop_id,
                    origin_stop.name AS origin_stop_name,
                    destination_stop.name AS destination_stop_name,
                    origin.departure_seconds,
                    destination.arrival_seconds - origin.departure_seconds AS duration_seconds,
                    trip.feed_id,
                    trip.shape_id,
                    origin.shape_position AS origin_shape_position,
                    destination.shape_position AS destination_shape_position,
                    destination.shape_progress_m - origin.shape_progress_m AS distance_m
                FROM realtime.vehicle_current_states AS vehicle
                JOIN core.gtfs_stop_times AS origin
                  ON origin.feed_id = vehicle.feed_id
                 AND origin.trip_id = vehicle.trip_id
                 AND origin.shape_progress_m >= vehicle.shape_progress_m
                JOIN core.gtfs_stop_times AS destination
                  ON destination.feed_id = origin.feed_id
                 AND destination.trip_id = origin.trip_id
                 AND destination.stop_sequence = origin.stop_sequence + 1
                JOIN core.gtfs_trips AS trip
                  ON trip.feed_id = origin.feed_id AND trip.trip_id = origin.trip_id
                JOIN core.gtfs_stops AS origin_stop
                  ON origin_stop.feed_id = origin.feed_id AND origin_stop.stop_id = origin.stop_id
                JOIN core.gtfs_stops AS destination_stop
                  ON destination_stop.feed_id = destination.feed_id
                 AND destination_stop.stop_id = destination.stop_id
                WHERE vehicle.source_timestamp >= :vehicle_cutoff
                  AND vehicle.trip_id IS NOT NULL
                  AND vehicle.shape_progress_m IS NOT NULL
                  AND destination.arrival_seconds > origin.departure_seconds
                  AND origin.shape_position IS NOT NULL
                  AND destination.shape_position IS NOT NULL
                  AND destination.shape_position > origin.shape_position
                  AND origin.shape_progress_m IS NOT NULL
                  AND destination.shape_progress_m > origin.shape_progress_m
            ),
            representatives AS (
                SELECT DISTINCT ON (origin_stop_id, destination_stop_id)
                    origin_stop_id, destination_stop_id,
                    origin_stop_name, destination_stop_name,
                    feed_id, shape_id, origin_shape_position, destination_shape_position,
                    distance_m
                FROM active_traversals
                ORDER BY origin_stop_id, destination_stop_id, duration_seconds DESC
            ),
            segment_geometries AS (
                SELECT representative.origin_stop_id,
                       representative.destination_stop_id,
                       representative.origin_stop_name,
                       representative.destination_stop_name,
                       representative.distance_m,
                       ST_SimplifyPreserveTopology(
                           ST_LineSubstring(
                               shape.geometry,
                               representative.origin_shape_position,
                               representative.destination_shape_position
                           ),
                           0.00003
                       ) AS geometry
                FROM representatives AS representative
                JOIN core.gtfs_shapes AS shape
                  ON shape.feed_id = representative.feed_id
                 AND shape.shape_id = representative.shape_id
            ),
            planned_slots AS (
                SELECT origin_stop_id, destination_stop_id,
                       AVG(duration_seconds)::float AS mean_seconds,
                       COUNT(*)::integer AS sample_count
                FROM active_traversals
                GROUP BY origin_stop_id, destination_stop_id
            )
            SELECT
                representative.origin_stop_id,
                representative.destination_stop_id,
                representative.origin_stop_name,
                representative.destination_stop_name,
                ST_AsGeoJSON(representative.geometry, 6)::json AS geometry,
                representative.distance_m,
                COALESCE(
                    live.mean_seconds,
                    historical.mean_seconds,
                    planned.mean_seconds
                ) AS duration_seconds,
                CASE WHEN live.mean_seconds IS NOT NULL THEN 'live'
                     WHEN historical.mean_seconds IS NOT NULL THEN 'historical'
                     ELSE 'gtfs_planned' END AS source,
                COALESCE(live.reliability, historical.reliability, 1.0) AS reliability,
                COALESCE(live.sample_count_accepted, historical.sample_count_accepted,
                         planned.sample_count, 0) AS sample_count,
                live.window_start, live.window_end,
                historical.slot_offset_minutes
            FROM segment_geometries AS representative
            LEFT JOIN LATERAL (
                SELECT mean_seconds, reliability, sample_count_accepted,
                       window_start, window_end
                FROM analytics.segment_live_metrics_5m
                WHERE scope = 'physical'
                  AND origin_stop_id = representative.origin_stop_id
                  AND destination_stop_id = representative.destination_stop_id
                  AND mean_seconds IS NOT NULL AND sample_count_accepted > 0
                  AND window_start <= :generated_at
                  AND window_end >= :live_cutoff
                ORDER BY window_end DESC LIMIT 1
            ) AS live ON true
            LEFT JOIN LATERAL (
                SELECT mean_seconds, reliability, sample_count_accepted,
                       CASE
                         WHEN slot_index - :slot_index > 144
                           THEN (slot_index - :slot_index - 288) * 5
                         WHEN slot_index - :slot_index < -144
                           THEN (slot_index - :slot_index + 288) * 5
                         ELSE (slot_index - :slot_index) * 5
                       END AS slot_offset_minutes
                FROM analytics.segment_profiles_5m
                WHERE scope = 'physical'
                  AND origin_stop_id = representative.origin_stop_id
                  AND destination_stop_id = representative.destination_stop_id
                  AND day_type = :day_type
                  AND reference_start_date = :reference_start
                  AND reference_end_date = :reference_end
                  AND mean_seconds IS NOT NULL AND sample_count_accepted > 0
                  AND LEAST(ABS(slot_index - :slot_index), 288 - ABS(slot_index - :slot_index)) <= 6
                ORDER BY LEAST(ABS(slot_index - :slot_index), 288 - ABS(slot_index - :slot_index)),
                         slot_index >= :slot_index DESC
                LIMIT 1
            ) AS historical ON live.mean_seconds IS NULL
            LEFT JOIN LATERAL (
                SELECT mean_seconds, sample_count
                FROM planned_slots
                WHERE origin_stop_id = representative.origin_stop_id
                  AND destination_stop_id = representative.destination_stop_id
                LIMIT 1
            ) AS planned ON live.mean_seconds IS NULL AND historical.mean_seconds IS NULL
            WHERE NOT ST_IsEmpty(representative.geometry)
              AND COALESCE(live.mean_seconds, historical.mean_seconds, planned.mean_seconds) > 0
            ORDER BY representative.origin_stop_id, representative.destination_stop_id
            """
        ),
        {
            "generated_at": generated_at,
            "live_cutoff": generated_at - timedelta(hours=1),
            "vehicle_cutoff": generated_at - timedelta(minutes=5),
            "service_date": service_date,
            "day_type": day_type,
            "slot_index": slot_index,
            "reference_start": historical_retention_start(service_date),
            "reference_end": service_date - timedelta(days=1),
        },
    )

    segments: list[SegmentSpeedMapItem] = []
    source_counts = {"live": 0, "historical": 0, "gtfs_planned": 0}
    for row in result.mappings():
        duration_seconds = float(row["duration_seconds"])
        distance_m = float(row["distance_m"])
        source = row["source"]
        source_counts[source] += 1
        segments.append(
            SegmentSpeedMapItem(
                segment_id=f'{row["origin_stop_id"]}>{row["destination_stop_id"]}',
                origin_stop_id=row["origin_stop_id"],
                origin_stop_name=row["origin_stop_name"],
                destination_stop_id=row["destination_stop_id"],
                destination_stop_name=row["destination_stop_name"],
                distance_m=distance_m,
                speed_kmh=distance_m / duration_seconds * 3.6,
                duration_seconds=duration_seconds,
                source=source,
                reliability=float(row["reliability"]),
                sample_count=int(row["sample_count"]),
                window_start=row["window_start"],
                window_end=row["window_end"],
                historical_offset_minutes=row["slot_offset_minutes"],
                geometry=_decode_geometry(row["geometry"]),
            )
        )

    return SegmentSpeedMapResponse(
        generated_at=generated_at,
        count=len(segments),
        source_counts=source_counts,
        segments=segments,
    )
