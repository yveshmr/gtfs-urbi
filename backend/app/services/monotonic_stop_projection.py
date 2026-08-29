from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class StopProjectionCandidate:
    segment_sequence: int
    progress_m: float
    shape_position: float
    distance_to_shape_m: float


@dataclass(frozen=True, slots=True)
class StopProjectionResult:
    pattern_count: int
    fallback_pattern_count: int
    assigned_stop_count: int
    updated_stop_time_count: int


def select_monotonic_stop_path(
    candidate_windows: tuple[tuple[StopProjectionCandidate, ...], ...],
) -> tuple[StopProjectionCandidate, ...] | None:
    if not candidate_windows or any(not candidates for candidates in candidate_windows):
        return None

    paths: tuple[tuple[float, tuple[StopProjectionCandidate, ...]], ...] = tuple(
        (candidate.distance_to_shape_m, (candidate,)) for candidate in candidate_windows[0]
    )

    for candidates in candidate_windows[1:]:
        next_paths: list[tuple[float, tuple[StopProjectionCandidate, ...]]] = []
        for candidate in candidates:
            predecessors = tuple(
                (cost, path) for cost, path in paths if candidate.progress_m >= path[-1].progress_m
            )
            if not predecessors:
                continue
            previous_cost, previous_path = min(
                predecessors,
                key=lambda item: (
                    item[0],
                    item[1][-1].progress_m,
                ),
            )
            next_paths.append(
                (
                    previous_cost + candidate.distance_to_shape_m,
                    (*previous_path, candidate),
                )
            )
        paths = tuple(next_paths)
        if not paths:
            return None

    _, selected_path = min(
        paths,
        key=lambda item: (
            item[0],
            item[1][-1].progress_m,
        ),
    )
    return selected_path


_PATTERN_CTE = """
WITH trip_patterns AS (
    SELECT
        trip.feed_id,
        trip.shape_id,
        array_agg(stop_time.stop_id ORDER BY stop_time.stop_sequence) AS stop_ids
    FROM core.gtfs_trips AS trip
    JOIN core.gtfs_stop_times AS stop_time
      ON stop_time.feed_id = trip.feed_id
     AND stop_time.trip_id = trip.trip_id
    WHERE trip.feed_id = :feed_id
      AND trip.shape_id IS NOT NULL
    GROUP BY trip.feed_id, trip.trip_id, trip.shape_id
), patterns AS (
    SELECT
        row_number() OVER (ORDER BY shape_id, stop_ids)::bigint AS pattern_id,
        feed_id,
        shape_id,
        stop_ids
    FROM (
        SELECT DISTINCT feed_id, shape_id, stop_ids
        FROM trip_patterns
    ) AS distinct_patterns
)
"""

PATTERNS_SQL = (
    _PATTERN_CTE
    + """
SELECT pattern_id, stop_ids
FROM patterns
ORDER BY pattern_id
"""
)

CANDIDATES_SQL = (
    _PATTERN_CTE
    + """
, pattern_stops AS (
    SELECT
        pattern.pattern_id,
        pattern.feed_id,
        pattern.shape_id,
        stop.stop_id,
        stop.ordinality::integer AS stop_ordinal
    FROM patterns AS pattern
    CROSS JOIN LATERAL unnest(pattern.stop_ids) WITH ORDINALITY AS stop(stop_id, ordinality)
)
SELECT DISTINCT
    pattern_stop.pattern_id,
    pattern_stop.stop_ordinal,
    candidate.segment_sequence,
    candidate.progress_m,
    candidate.shape_position,
    candidate.distance_to_shape_m
FROM pattern_stops AS pattern_stop
JOIN core.gtfs_stops AS stop
  ON stop.feed_id = pattern_stop.feed_id
 AND stop.stop_id = pattern_stop.stop_id
JOIN LATERAL (
    SELECT
        segment.segment_sequence,
        segment.start_distance_m
            + ST_LineLocatePoint(segment.geometry, stop.location)
            * segment.segment_length_m AS progress_m,
        segment.start_fraction
            + ST_LineLocatePoint(segment.geometry, stop.location)
            * (segment.end_fraction - segment.start_fraction) AS shape_position,
        ST_Distance(segment.geometry::geography, stop.location::geography)
            AS distance_to_shape_m
    FROM core.gtfs_shape_segments AS segment
    WHERE segment.feed_id = pattern_stop.feed_id
      AND segment.shape_id = pattern_stop.shape_id
      AND segment.geometry && ST_Expand(stop.location, 0.001)
      AND ST_DWithin(segment.geometry::geography, stop.location::geography, 50)

    UNION

    SELECT
        nearest.segment_sequence,
        nearest.start_distance_m
            + ST_LineLocatePoint(nearest.geometry, stop.location)
            * nearest.segment_length_m,
        nearest.start_fraction
            + ST_LineLocatePoint(nearest.geometry, stop.location)
            * (nearest.end_fraction - nearest.start_fraction),
        ST_Distance(nearest.geometry::geography, stop.location::geography)
    FROM (
        SELECT segment.*
        FROM core.gtfs_shape_segments AS segment
        WHERE segment.feed_id = pattern_stop.feed_id
          AND segment.shape_id = pattern_stop.shape_id
        ORDER BY segment.geometry <-> stop.location
        LIMIT 1
    ) AS nearest
) AS candidate ON stop.location IS NOT NULL
ORDER BY pattern_stop.pattern_id, pattern_stop.stop_ordinal, candidate.progress_m
"""
)

EXPANDED_CANDIDATES_SQL = (
    _PATTERN_CTE
    + """
, pattern_stops AS (
    SELECT
        pattern.pattern_id,
        pattern.feed_id,
        pattern.shape_id,
        stop.stop_id,
        stop.ordinality::integer AS stop_ordinal
    FROM patterns AS pattern
    CROSS JOIN LATERAL unnest(pattern.stop_ids) WITH ORDINALITY AS stop(stop_id, ordinality)
    WHERE pattern.pattern_id = ANY(CAST(:pattern_ids AS bigint[]))
)
SELECT
    pattern_stop.pattern_id,
    pattern_stop.stop_ordinal,
    segment.segment_sequence,
    segment.start_distance_m
        + ST_LineLocatePoint(segment.geometry, stop.location)
        * segment.segment_length_m AS progress_m,
    segment.start_fraction
        + ST_LineLocatePoint(segment.geometry, stop.location)
        * (segment.end_fraction - segment.start_fraction) AS shape_position,
    ST_Distance(segment.geometry::geography, stop.location::geography)
        AS distance_to_shape_m
FROM pattern_stops AS pattern_stop
JOIN core.gtfs_stops AS stop
  ON stop.feed_id = pattern_stop.feed_id
 AND stop.stop_id = pattern_stop.stop_id
JOIN core.gtfs_shape_segments AS segment
  ON segment.feed_id = pattern_stop.feed_id
 AND segment.shape_id = pattern_stop.shape_id
WHERE stop.location IS NOT NULL
ORDER BY pattern_stop.pattern_id, pattern_stop.stop_ordinal, progress_m
"""
)

UPDATE_STOP_TIMES_SQL = """
WITH trip_patterns AS (
    SELECT
        trip.feed_id,
        trip.trip_id,
        trip.shape_id,
        array_agg(stop_time.stop_id ORDER BY stop_time.stop_sequence) AS stop_ids
    FROM core.gtfs_trips AS trip
    JOIN core.gtfs_stop_times AS stop_time
      ON stop_time.feed_id = trip.feed_id
     AND stop_time.trip_id = trip.trip_id
    WHERE trip.feed_id = :feed_id
      AND trip.shape_id IS NOT NULL
    GROUP BY trip.feed_id, trip.trip_id, trip.shape_id
), patterns AS (
    SELECT
        row_number() OVER (ORDER BY shape_id, stop_ids)::bigint AS pattern_id,
        feed_id,
        shape_id,
        stop_ids
    FROM (
        SELECT DISTINCT feed_id, shape_id, stop_ids
        FROM trip_patterns
    ) AS distinct_patterns
), members AS (
    SELECT trip.feed_id, trip.trip_id, pattern.pattern_id
    FROM trip_patterns AS trip
    JOIN patterns AS pattern
      ON pattern.feed_id = trip.feed_id
     AND pattern.shape_id = trip.shape_id
     AND pattern.stop_ids = trip.stop_ids
), ordered_stop_times AS (
    SELECT
        stop_time.feed_id,
        stop_time.trip_id,
        stop_time.stop_sequence,
        row_number() OVER (
            PARTITION BY stop_time.feed_id, stop_time.trip_id
            ORDER BY stop_time.stop_sequence
        )::integer AS stop_ordinal
    FROM core.gtfs_stop_times AS stop_time
    WHERE stop_time.feed_id = :feed_id
)
UPDATE core.gtfs_stop_times AS stop_time
SET
    shape_position = assignment.shape_position,
    shape_progress_m = assignment.shape_progress_m,
    distance_to_shape_m = assignment.distance_to_shape_m,
    shape_projection_quality = assignment.projection_quality
FROM ordered_stop_times AS ordered
JOIN members AS member
  ON member.feed_id = ordered.feed_id
 AND member.trip_id = ordered.trip_id
JOIN _gtfs_monotonic_stop_assignments AS assignment
  ON assignment.pattern_id = member.pattern_id
 AND assignment.stop_ordinal = ordered.stop_ordinal
WHERE stop_time.feed_id = ordered.feed_id
  AND stop_time.trip_id = ordered.trip_id
  AND stop_time.stop_sequence = ordered.stop_sequence
"""


def _append_candidates(
    windows: dict[int, list[list[StopProjectionCandidate]]],
    rows: Iterable[object],
) -> None:
    for row in rows:
        windows[row["pattern_id"]][row["stop_ordinal"] - 1].append(
            StopProjectionCandidate(
                segment_sequence=row["segment_sequence"],
                progress_m=row["progress_m"],
                shape_position=row["shape_position"],
                distance_to_shape_m=row["distance_to_shape_m"],
            )
        )


async def _copy_assignments(
    session: AsyncSession,
    rows: Iterable[Sequence[object]],
) -> int:
    connection = await session.connection()
    raw_connection = await connection.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    count = 0
    async with driver_connection.cursor() as cursor:
        async with cursor.copy(
            """
            COPY _gtfs_monotonic_stop_assignments
                (pattern_id, stop_ordinal, shape_position, shape_progress_m,
                 distance_to_shape_m, projection_quality)
            FROM STDIN
            """
        ) as copy:
            for row in rows:
                await copy.write_row(row)
                count += 1
    return count


async def reproject_gtfs_stops_monotonically(
    session: AsyncSession,
    *,
    feed_id: uuid.UUID,
) -> StopProjectionResult:
    pattern_result = await session.execute(text(PATTERNS_SQL), {"feed_id": feed_id})
    patterns = {row["pattern_id"]: len(row["stop_ids"]) for row in pattern_result.mappings()}
    windows: dict[int, list[list[StopProjectionCandidate]]] = {
        pattern_id: [[] for _ in range(stop_count)] for pattern_id, stop_count in patterns.items()
    }
    candidate_result = await session.execute(text(CANDIDATES_SQL), {"feed_id": feed_id})
    _append_candidates(windows, candidate_result.mappings())

    fallback_pattern_ids = [
        pattern_id
        for pattern_id, candidate_windows in windows.items()
        if select_monotonic_stop_path(tuple(tuple(candidates) for candidates in candidate_windows))
        is None
    ]
    if fallback_pattern_ids:
        for pattern_id in fallback_pattern_ids:
            windows[pattern_id] = [[] for _ in range(patterns[pattern_id])]
        expanded_result = await session.execute(
            text(EXPANDED_CANDIDATES_SQL),
            {"feed_id": feed_id, "pattern_ids": fallback_pattern_ids},
        )
        _append_candidates(windows, expanded_result.mappings())

    assignments: list[tuple[object, ...]] = []
    for pattern_id, candidate_windows in windows.items():
        path = select_monotonic_stop_path(
            tuple(tuple(candidates) for candidates in candidate_windows)
        )
        if path is None:
            raise ValueError("GTFS stop pattern has no monotonic projection.")
        assignments.extend(
            (
                pattern_id,
                ordinal,
                candidate.shape_position,
                candidate.progress_m,
                candidate.distance_to_shape_m,
                (
                    "valid"
                    if candidate.distance_to_shape_m <= 30
                    else "reduced"
                    if candidate.distance_to_shape_m <= 50
                    else "fallback_required"
                ),
            )
            for ordinal, candidate in enumerate(path, start=1)
        )

    await session.execute(text("DROP TABLE IF EXISTS _gtfs_monotonic_stop_assignments"))
    await session.execute(
        text(
            """
            CREATE TEMP TABLE _gtfs_monotonic_stop_assignments (
                pattern_id bigint NOT NULL,
                stop_ordinal integer NOT NULL,
                shape_position double precision NOT NULL,
                shape_progress_m double precision NOT NULL,
                distance_to_shape_m double precision NOT NULL,
                projection_quality varchar(30) NOT NULL,
                PRIMARY KEY (pattern_id, stop_ordinal)
            ) ON COMMIT DROP
            """
        )
    )
    assigned_count = await _copy_assignments(session, assignments)
    update_result = await session.execute(text(UPDATE_STOP_TIMES_SQL), {"feed_id": feed_id})
    await session.execute(text("DROP TABLE _gtfs_monotonic_stop_assignments"))
    return StopProjectionResult(
        pattern_count=len(patterns),
        fallback_pattern_count=len(fallback_pattern_ids),
        assigned_stop_count=assigned_count,
        updated_stop_time_count=update_result.rowcount,
    )
