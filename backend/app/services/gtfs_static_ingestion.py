from __future__ import annotations

import csv
import io
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.gtfs_static import GtfsStaticDownload
from app.models import ApiResponse, GtfsFeed, IngestionRun
from app.services.monotonic_stop_projection import reproject_gtfs_stops_monotonically

REQUIRED_FILES = {
    "agency.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "feed_info.txt",
    "routes.txt",
    "shapes.txt",
    "stop_times.txt",
    "stops.txt",
    "trips.txt",
}

COPY_AGENCIES = """
COPY core.gtfs_agencies
    (feed_id, agency_id, name, url, timezone, language, phone)
FROM STDIN
"""
COPY_SERVICES = """
COPY core.gtfs_services
    (feed_id, service_id, monday, tuesday, wednesday, thursday, friday,
     saturday, sunday, start_date, end_date)
FROM STDIN
"""
COPY_SERVICE_EXCEPTIONS = """
COPY core.gtfs_service_exceptions
    (feed_id, service_id, service_date, exception_type)
FROM STDIN
"""
COPY_ROUTES = """
COPY core.gtfs_routes
    (feed_id, route_id, agency_id, short_name, long_name, description,
     route_type, color, text_color)
FROM STDIN
"""
COPY_SHAPES = """
COPY core.gtfs_shapes
    (feed_id, shape_id, geometry, point_count)
FROM STDIN
"""
COPY_SHAPE_POINTS = """
COPY core.gtfs_shape_points
    (feed_id, shape_id, sequence, latitude, longitude, distance_traveled, location)
FROM STDIN
"""
COPY_STOPS = """
COPY core.gtfs_stops
    (feed_id, stop_id, code, name, description, latitude, longitude, zone_id,
     url, location_type, parent_station, location)
FROM STDIN
"""
COPY_TRIPS = """
COPY core.gtfs_trips
    (feed_id, trip_id, route_id, service_id, headsign, direction_id,
     start_seconds, block_id, shape_id)
FROM STDIN
"""
COPY_STOP_TIMES = """
COPY core.gtfs_stop_times
    (feed_id, trip_id, stop_sequence, stop_id, arrival_seconds, departure_seconds,
     stop_headsign, pickup_type, drop_off_type, timepoint)
FROM STDIN
"""
PROJECT_STOP_TIMES = """
UPDATE core.gtfs_stop_times AS stop_time
SET
    shape_position = ST_LineLocatePoint(shape.geometry, stop.location),
    shape_progress_m = ST_LineLocatePoint(shape.geometry, stop.location)
        * shape_total.total_distance_m,
    distance_to_shape_m = ST_Distance(
        stop.location::geography,
        ST_ClosestPoint(shape.geometry, stop.location)::geography
    ),
    shape_projection_quality = CASE
        WHEN ST_Distance(
            stop.location::geography,
            ST_ClosestPoint(shape.geometry, stop.location)::geography
        ) <= 30 THEN 'valid'
        WHEN ST_Distance(
            stop.location::geography,
            ST_ClosestPoint(shape.geometry, stop.location)::geography
        ) <= 50 THEN 'reduced'
        ELSE 'fallback_required'
    END
FROM core.gtfs_trips AS trip
JOIN core.gtfs_shapes AS shape
  ON shape.feed_id = trip.feed_id
 AND shape.shape_id = trip.shape_id
JOIN LATERAL (
    SELECT max(segment.end_distance_m) AS total_distance_m
    FROM core.gtfs_shape_segments AS segment
    WHERE segment.feed_id = shape.feed_id
      AND segment.shape_id = shape.shape_id
) AS shape_total ON true
JOIN core.gtfs_stops AS stop
  ON stop.feed_id = trip.feed_id
WHERE stop_time.feed_id = :feed_id
  AND trip.feed_id = :feed_id
  AND stop_time.feed_id = trip.feed_id
  AND stop_time.trip_id = trip.trip_id
  AND stop.stop_id = stop_time.stop_id
  AND stop.location IS NOT NULL
"""
MATERIALIZE_SHAPE_SEGMENTS = """
WITH point_pairs AS (
    SELECT
        point.feed_id,
        point.shape_id,
        point.sequence AS segment_sequence,
        point.location AS start_location,
        lead(point.location) OVER (
            PARTITION BY point.feed_id, point.shape_id
            ORDER BY point.sequence
        ) AS end_location
    FROM core.gtfs_shape_points AS point
    WHERE point.feed_id = :feed_id
), measured AS (
    SELECT
        feed_id,
        shape_id,
        segment_sequence,
        ST_MakeLine(start_location, end_location) AS geometry,
        ST_Distance(start_location::geography, end_location::geography) AS segment_length_m,
        degrees(ST_Azimuth(start_location, end_location)) AS bearing_degrees
    FROM point_pairs
    WHERE end_location IS NOT NULL
      AND NOT ST_Equals(start_location, end_location)
), positioned AS (
    SELECT
        measured.*,
        coalesce(
            sum(segment_length_m) OVER (
                PARTITION BY feed_id, shape_id
                ORDER BY segment_sequence
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0
        ) AS start_distance_m,
        sum(segment_length_m) OVER (
            PARTITION BY feed_id, shape_id
        ) AS total_distance_m
    FROM measured
)
INSERT INTO core.gtfs_shape_segments (
    feed_id,
    shape_id,
    segment_sequence,
    geometry,
    segment_length_m,
    start_distance_m,
    end_distance_m,
    start_fraction,
    end_fraction,
    bearing_degrees
)
SELECT
    feed_id,
    shape_id,
    segment_sequence,
    geometry,
    segment_length_m,
    start_distance_m,
    start_distance_m + segment_length_m,
    start_distance_m / total_distance_m,
    (start_distance_m + segment_length_m) / total_distance_m,
    bearing_degrees
FROM positioned
WHERE total_distance_m > 0
"""


class GtfsStaticSource(Protocol):
    async def download(self) -> GtfsStaticDownload: ...


@dataclass(frozen=True, slots=True)
class GtfsFeedMetadata:
    publisher_name: str | None
    publisher_url: str | None
    language: str | None
    start_date: date | None
    end_date: date | None
    version: str | None


def parse_gtfs_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def parse_gtfs_time(value: str) -> int:
    hour, minute, second = (int(part) for part in value.split(":"))
    return hour * 3600 + minute * 60 + second


def optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def optional_int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def optional_float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


class GtfsArchive:
    def __init__(self, content: bytes) -> None:
        self._buffer = io.BytesIO(content)
        self._archive = zipfile.ZipFile(self._buffer)
        available = set(self._archive.namelist())
        missing = REQUIRED_FILES - available
        if missing:
            raise ValueError(f"GTFS archive is missing required files: {sorted(missing)}")

    @property
    def file_names(self) -> list[str]:
        return sorted(self._archive.namelist())

    def rows(self, name: str) -> Iterator[dict[str, str]]:
        with self._archive.open(name) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
            yield from reader

    def metadata(self) -> GtfsFeedMetadata:
        row = next(self.rows("feed_info.txt"), {})
        return GtfsFeedMetadata(
            publisher_name=optional_string(row.get("feed_publisher_name")),
            publisher_url=optional_string(row.get("feed_publisher_url")),
            language=optional_string(row.get("feed_lang")),
            start_date=parse_gtfs_date(row.get("feed_start_date")),
            end_date=parse_gtfs_date(row.get("feed_end_date")),
            version=optional_string(row.get("feed_version")),
        )


async def _copy_rows(
    session: AsyncSession,
    copy_sql: str,
    rows: Iterable[Sequence[object]],
) -> int:
    connection = await session.connection()
    raw_connection = await connection.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    count = 0
    async with driver_connection.cursor() as cursor:
        async with cursor.copy(copy_sql) as copy:
            for row in rows:
                await copy.write_row(row)
                count += 1
    return count


def _point_ewkt(longitude: float, latitude: float) -> str:
    return f"SRID=4326;POINT({longitude} {latitude})"


def _line_ewkt(points: Sequence[tuple[int, float, float, float | None]]) -> str:
    ordered = sorted(points, key=lambda point: point[0])
    coordinates = ",".join(f"{longitude} {latitude}" for _, latitude, longitude, _ in ordered)
    return f"SRID=4326;LINESTRING({coordinates})"


async def _load_feed_tables(
    session: AsyncSession,
    archive: GtfsArchive,
    feed_id: uuid.UUID,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    feed = str(feed_id)

    agencies = list(archive.rows("agency.txt"))
    counts["agencies"] = await _copy_rows(
        session,
        COPY_AGENCIES,
        (
            (
                feed,
                row.get("agency_id", "").strip(),
                row["agency_name"],
                row["agency_url"],
                row["agency_timezone"],
                optional_string(row.get("agency_lang")),
                optional_string(row.get("agency_phone")),
            )
            for row in agencies
        ),
    )

    calendar_rows = list(archive.rows("calendar.txt"))
    exception_rows = list(archive.rows("calendar_dates.txt"))
    services_by_id = {row["service_id"]: row for row in calendar_rows}
    for exception in exception_rows:
        services_by_id.setdefault(exception["service_id"], {})
    counts["services"] = await _copy_rows(
        session,
        COPY_SERVICES,
        (
            (
                feed,
                service_id,
                row.get("monday") == "1",
                row.get("tuesday") == "1",
                row.get("wednesday") == "1",
                row.get("thursday") == "1",
                row.get("friday") == "1",
                row.get("saturday") == "1",
                row.get("sunday") == "1",
                parse_gtfs_date(row.get("start_date")),
                parse_gtfs_date(row.get("end_date")),
            )
            for service_id, row in services_by_id.items()
        ),
    )
    counts["service_exceptions"] = await _copy_rows(
        session,
        COPY_SERVICE_EXCEPTIONS,
        (
            (
                feed,
                row["service_id"],
                parse_gtfs_date(row["date"]),
                int(row["exception_type"]),
            )
            for row in exception_rows
        ),
    )

    counts["routes"] = await _copy_rows(
        session,
        COPY_ROUTES,
        (
            (
                feed,
                row["route_id"],
                optional_string(row.get("agency_id")),
                optional_string(row.get("route_short_name")),
                optional_string(row.get("route_long_name")),
                optional_string(row.get("route_desc")),
                int(row["route_type"]),
                optional_string(row.get("route_color")),
                optional_string(row.get("route_text_color")),
            )
            for row in archive.rows("routes.txt")
        ),
    )

    shape_points: dict[str, list[tuple[int, float, float, float | None]]] = defaultdict(list)
    for row in archive.rows("shapes.txt"):
        shape_points[row["shape_id"]].append(
            (
                int(row["shape_pt_sequence"]),
                float(row["shape_pt_lat"]),
                float(row["shape_pt_lon"]),
                optional_float(row.get("shape_dist_traveled")),
            )
        )
    counts["shapes"] = await _copy_rows(
        session,
        COPY_SHAPES,
        (
            (feed, shape_id, _line_ewkt(points), len(points))
            for shape_id, points in shape_points.items()
        ),
    )
    counts["shape_points"] = await _copy_rows(
        session,
        COPY_SHAPE_POINTS,
        (
            (
                feed,
                shape_id,
                sequence,
                latitude,
                longitude,
                distance,
                _point_ewkt(longitude, latitude),
            )
            for shape_id, points in shape_points.items()
            for sequence, latitude, longitude, distance in points
        ),
    )

    counts["stops"] = await _copy_rows(
        session,
        COPY_STOPS,
        (
            (
                feed,
                row["stop_id"],
                optional_string(row.get("stop_code")),
                row["stop_name"],
                optional_string(row.get("stop_desc")),
                latitude,
                longitude,
                optional_string(row.get("zone_id")),
                optional_string(row.get("stop_url")),
                optional_int(row.get("location_type")),
                optional_string(row.get("parent_station")),
                _point_ewkt(longitude, latitude)
                if latitude is not None and longitude is not None
                else None,
            )
            for row in archive.rows("stops.txt")
            for latitude, longitude in [
                (optional_float(row.get("stop_lat")), optional_float(row.get("stop_lon")))
            ]
        ),
    )

    first_departure_by_trip: dict[str, tuple[int, int]] = {}
    for row in archive.rows("stop_times.txt"):
        sequence = int(row["stop_sequence"])
        current = first_departure_by_trip.get(row["trip_id"])
        if current is None or sequence < current[0]:
            first_departure_by_trip[row["trip_id"]] = (
                sequence,
                parse_gtfs_time(row["departure_time"]),
            )

    counts["trips"] = await _copy_rows(
        session,
        COPY_TRIPS,
        (
            (
                feed,
                row["trip_id"],
                row["route_id"],
                row["service_id"],
                optional_string(row.get("trip_headsign")),
                optional_int(row.get("direction_id")),
                first_departure_by_trip.get(row["trip_id"], (0, None))[1],
                optional_string(row.get("block_id")),
                optional_string(row.get("shape_id")),
            )
            for row in archive.rows("trips.txt")
        ),
    )

    counts["stop_times"] = await _copy_rows(
        session,
        COPY_STOP_TIMES,
        (
            (
                feed,
                row["trip_id"],
                int(row["stop_sequence"]),
                row["stop_id"],
                parse_gtfs_time(row["arrival_time"]),
                parse_gtfs_time(row["departure_time"]),
                optional_string(row.get("stop_headsign")),
                optional_int(row.get("pickup_type")),
                optional_int(row.get("drop_off_type")),
                optional_int(row.get("timepoint")),
            )
            for row in archive.rows("stop_times.txt")
        ),
    )
    return counts


async def ingest_gtfs_static(session: AsyncSession, source: GtfsStaticSource) -> IngestionRun:
    run = IngestionRun(
        source_system="cittati",
        resource_name="gtfs_static",
        status="running",
    )
    session.add(run)
    await session.flush()

    try:
        download = await source.download()
        archive = GtfsArchive(download.content)
        metadata = archive.metadata()
        existing_feed_id = await session.scalar(
            select(GtfsFeed.id).where(GtfsFeed.content_hash == download.content_hash)
        )

        if existing_feed_id is None:
            feed = GtfsFeed(
                source_system="cittati",
                source_url=download.source_url,
                content_hash=download.content_hash,
                retrieved_at=download.received_at,
                source_last_modified=download.source_last_modified,
                publisher_name=metadata.publisher_name,
                publisher_url=metadata.publisher_url,
                language=metadata.language,
                feed_start_date=metadata.start_date,
                feed_end_date=metadata.end_date,
                feed_version=metadata.version,
            )
            session.add(feed)
            await session.flush()
            counts = await _load_feed_tables(session, archive, feed.id)
            segment_result = await session.execute(
                text(MATERIALIZE_SHAPE_SEGMENTS),
                {"feed_id": feed.id},
            )
            counts["shape_segments"] = segment_result.rowcount
            await session.execute(text(PROJECT_STOP_TIMES), {"feed_id": feed.id})
            stop_projection = await reproject_gtfs_stops_monotonically(
                session,
                feed_id=feed.id,
            )
            counts["monotonic_stop_patterns"] = stop_projection.pattern_count
            feed_id = feed.id
            duplicate = False
        else:
            counts = {}
            feed_id = existing_feed_id
            duplicate = True

        payload = {
            "feed_id": str(feed_id),
            "duplicate": duplicate,
            "files": archive.file_names,
            "row_counts": counts,
        }
        session.add(
            ApiResponse(
                ingestion_run_id=run.id,
                endpoint_name="gtfs_static",
                source_model="gtfs-static",
                requested_at=download.requested_at,
                received_at=download.received_at,
                source_timestamp=download.source_last_modified,
                duration_ms=download.duration_ms,
                http_status=download.http_status,
                payload_hash=download.content_hash,
                request_params={},
                payload=payload,
            )
        )
        total_rows = sum(counts.values())
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        run.records_received = total_rows
        run.records_written = total_rows
        run.http_status = download.http_status
        run.run_metadata = {"feed_id": str(feed_id), "duplicate": duplicate}
        await session.commit()
        return run
    except Exception as error:
        await session.rollback()
        failed_run = IngestionRun(
            source_system="cittati",
            resource_name="gtfs_static",
            status="failed",
            finished_at=datetime.now(UTC),
            error_message=f"{type(error).__name__}: {error}",
        )
        session.add(failed_run)
        await session.commit()
        raise
