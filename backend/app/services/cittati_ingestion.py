from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.cittati import CittatiRawResponse
from app.models import IngestionRun, VehicleCurrentState
from app.services.active_trip_index import ActiveTripIndex, load_active_trip_index
from app.services.historical_profile_refresh import (
    refresh_historical_profiles_if_due,
)
from app.services.segment_aggregation import (
    SegmentCompletionSample,
    aggregate_window,
    five_minute_window,
    historical_retention_start,
    metric_identities_for_segment,
    metric_reliability,
    metric_status,
    profile_slot,
)
from app.services.segment_crossing import (
    BoundaryCrossing,
    SegmentBoundary,
    complete_segments_from_crossings,
    interpolate_crossed_boundaries,
)
from app.services.segment_sample_validation import assess_segment_sample
from app.services.temporal_map_matching import (
    PositionSample,
    ShapeCandidate,
    match_three_samples,
)
from app.services.trip_correlation import correlate_exact_trip, normalize_model4_line

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_SOURCE_DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


class CittatiVehicleSource(Protocol):
    async def fetch_vehicles(self, *, model: int = 4) -> CittatiRawResponse: ...


@dataclass(frozen=True, slots=True)
class ParsedVehicleBatch:
    rows: list[dict[str, Any]]
    rejected_count: int
    duplicate_prefix_count: int
    invalid_location_count: int
    invalid_timestamp_count: int


@dataclass(frozen=True, slots=True)
class BoundaryProcessingResult:
    crossing_count: int
    completed_high_confidence: int
    completed_reduced_confidence: int
    observations_written: int
    observations_accepted: int
    rejected_speed: int
    rejected_mad: int
    live_metrics_updated: int
    daily_metrics_updated: int


@dataclass(frozen=True, slots=True)
class MetricRefreshResult:
    live_metrics_updated: int
    daily_metrics_updated: int


def count_vehicle_records(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0

    records = payload.get("dados")
    return len(records) if isinstance(records, list) else 0


def is_successful_vehicle_response(response: CittatiRawResponse) -> bool:
    if not 200 <= response.http_status < 300:
        return False

    if not isinstance(response.payload, dict):
        return False

    return isinstance(response.payload.get("campos"), list) and isinstance(
        response.payload.get("dados"), list
    )


def _text(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _float(value: object) -> float | None:
    text_value = _text(value)
    if text_value is None:
        return None
    try:
        return float(text_value.replace(",", "."))
    except ValueError:
        return None


def _source_timestamp(value: object) -> datetime | None:
    text_value = _text(value)
    if text_value is None:
        return None

    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None

    if parsed is None:
        for format_ in _SOURCE_DATETIME_FORMATS:
            try:
                parsed = datetime.strptime(text_value, format_)
                break
            except ValueError:
                continue

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_OPERATIONAL_TIMEZONE)
    return parsed.astimezone(UTC)


def _valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def parse_vehicle_batch(
    payload: Mapping[str, object],
    *,
    ingestion_run_id: object,
    payload_hash: str,
    received_at: datetime,
) -> ParsedVehicleBatch:
    fields = payload.get("campos")
    records = payload.get("dados")
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        return ParsedVehicleBatch([], 0, 0, 0, 0)
    if not isinstance(records, list):
        return ParsedVehicleBatch([], 0, 0, 0, 0)

    rows_by_prefix: dict[str, dict[str, Any]] = {}
    rejected_count = 0
    duplicate_prefix_count = 0
    invalid_location_count = 0
    invalid_timestamp_count = 0

    for source_row in records:
        if not isinstance(source_row, Sequence) or isinstance(source_row, (str, bytes)):
            rejected_count += 1
            continue
        if len(source_row) != len(fields):
            rejected_count += 1
            continue

        source_data = dict(zip(fields, source_row, strict=True))
        vehicle_prefix = _text(source_data.get("Prefixo"))
        if vehicle_prefix is None:
            rejected_count += 1
            continue

        latitude = _float(source_data.get("GPS_Latitude"))
        longitude = _float(source_data.get("GPS_Longitude"))
        coordinates_are_valid = _valid_coordinates(latitude, longitude)
        if not coordinates_are_valid:
            latitude = None
            longitude = None
            invalid_location_count += 1

        timestamp_value = source_data.get("DataHora")
        source_timestamp = _source_timestamp(timestamp_value)
        if _text(timestamp_value) is not None and source_timestamp is None:
            invalid_timestamp_count += 1

        speed_kmh = _float(source_data.get("Velocidade"))
        if speed_kmh is not None and speed_kmh < 0:
            speed_kmh = None

        if vehicle_prefix in rows_by_prefix:
            duplicate_prefix_count += 1

        rows_by_prefix[vehicle_prefix] = {
            "vehicle_prefix": vehicle_prefix,
            "imei": _text(source_data.get("IMEI")),
            "source_timestamp": source_timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "location": (
                f"SRID=4326;POINT({longitude} {latitude})" if coordinates_are_valid else None
            ),
            "gps_direction": _float(source_data.get("GPS_Direcao")),
            "speed_kmh": speed_kmh,
            "low_speed_since": (
                source_timestamp or received_at
                if speed_kmh is not None and speed_kmh < 1
                else None
            ),
            "current_line": _text(source_data.get("Linha_atual")),
            "normalized_current_line": normalize_model4_line(_text(source_data.get("Linha_atual"))),
            "current_planned_time": _text(source_data.get("HoraViagemPlanejada_atual")),
            "current_direction": _text(source_data.get("GTFS_Sentido_atual")),
            "current_schedule_position": _text(source_data.get("posicaoEscala_atual")),
            "current_actual_time": _text(source_data.get("HoraViagemRealizada_atual")),
            "next_planned_time": _text(source_data.get("HoraViagemPlanejada_proxima")),
            "next_trip_point": _text(source_data.get("pontoProxViagem")),
            "next_schedule_position": _text(source_data.get("posicaoEscala_proxima")),
            "next_line": _text(source_data.get("Linha_proxima")),
            "next_direction": _text(source_data.get("GTFS_Sentido_proxima")),
            "next_trip_destination": _text(source_data.get("destino_pontoProxViagem")),
            "feed_id": None,
            "trip_id": None,
            "route_id": None,
            "shape_id": None,
            "correlation_status": "fallback_required",
            "correlation_reason": "missing_input",
            "correlation_level": None,
            "correlation_candidate_count": 0,
            "shape_position": None,
            "shape_progress_m": None,
            "distance_to_shape_m": None,
            "projected_location": None,
            "projected_at": None,
            "projection_quality": None,
            "current_origin_stop_id": None,
            "current_destination_stop_id": None,
            "current_origin_stop_sequence": None,
            "current_destination_stop_sequence": None,
            "previous_state_1": None,
            "previous_state_2": None,
            "position_sample_count": 1,
            "map_match_status": "collecting",
            "last_boundary_stop_id": None,
            "last_boundary_stop_sequence": None,
            "last_boundary_progress_m": None,
            "last_boundary_projection_quality": None,
            "last_boundary_crossed_at": None,
            "last_boundary_observation_at": None,
            "source_data": source_data,
            "payload_hash": payload_hash,
            "ingestion_run_id": ingestion_run_id,
            "received_at": received_at,
            "updated_at": received_at,
        }

    return ParsedVehicleBatch(
        rows=list(rows_by_prefix.values()),
        rejected_count=rejected_count,
        duplicate_prefix_count=duplicate_prefix_count,
        invalid_location_count=invalid_location_count,
        invalid_timestamp_count=invalid_timestamp_count,
    )


def apply_exact_trip_correlations(
    rows: list[dict[str, Any]],
    index: ActiveTripIndex,
) -> None:
    for row in rows:
        result = correlate_exact_trip(
            line=row["current_line"],
            direction=row["current_direction"],
            planned_time=row["current_planned_time"],
            candidates_by_key=index.candidates_by_key,
        )
        row["correlation_status"] = result.status
        row["correlation_reason"] = result.reason
        row["correlation_candidate_count"] = result.candidate_count
        if result.trip_id is None:
            continue
        candidate = index.candidates_by_trip_id[result.trip_id]
        row["feed_id"] = candidate.feed_id
        row["trip_id"] = candidate.trip_id
        row["route_id"] = candidate.route_id
        row["shape_id"] = candidate.shape_id
        row["correlation_level"] = 1


async def _upsert_current_states(
    session: AsyncSession,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    statement = insert(VehicleCurrentState).values(rows)
    incoming_is_newer = func.coalesce(
        statement.excluded.source_timestamp,
        statement.excluded.received_at,
    ) > func.coalesce(
        VehicleCurrentState.source_timestamp,
        VehicleCurrentState.received_at,
    )
    trip_changed = or_(
        VehicleCurrentState.trip_id.is_distinct_from(statement.excluded.trip_id),
        VehicleCurrentState.shape_id.is_distinct_from(statement.excluded.shape_id),
    )
    sample_gap_exceeded = func.coalesce(
        statement.excluded.source_timestamp,
        statement.excluded.received_at,
    ) - func.coalesce(
        VehicleCurrentState.source_timestamp,
        VehicleCurrentState.received_at,
    ) > text("INTERVAL '5 minutes'")
    window_must_reset = or_(trip_changed, sample_gap_exceeded)
    previous_current_state = func.jsonb_build_object(
        "source_timestamp",
        VehicleCurrentState.source_timestamp,
        "latitude",
        VehicleCurrentState.latitude,
        "longitude",
        VehicleCurrentState.longitude,
        "gps_direction",
        VehicleCurrentState.gps_direction,
        "feed_id",
        VehicleCurrentState.feed_id,
        "trip_id",
        VehicleCurrentState.trip_id,
        "shape_id",
        VehicleCurrentState.shape_id,
        "shape_position",
        VehicleCurrentState.shape_position,
        "shape_progress_m",
        VehicleCurrentState.shape_progress_m,
        "distance_to_shape_m",
        VehicleCurrentState.distance_to_shape_m,
        "projection_quality",
        VehicleCurrentState.projection_quality,
        "map_match_status",
        VehicleCurrentState.map_match_status,
        "origin_stop_id",
        VehicleCurrentState.current_origin_stop_id,
        "destination_stop_id",
        VehicleCurrentState.current_destination_stop_id,
    )
    special_columns = {
        "vehicle_prefix",
        "previous_state_1",
        "previous_state_2",
        "position_sample_count",
        "map_match_status",
        "low_speed_since",
        "last_boundary_stop_id",
        "last_boundary_stop_sequence",
        "last_boundary_progress_m",
        "last_boundary_projection_quality",
        "last_boundary_crossed_at",
        "last_boundary_observation_at",
    }
    update_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in VehicleCurrentState.__table__.columns
        if column.name not in special_columns
    }
    update_columns.update(
        {
            "previous_state_2": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.previous_state_1,
            ),
            "previous_state_1": case(
                (window_must_reset, None),
                else_=previous_current_state,
            ),
            "position_sample_count": case(
                (window_must_reset, 1),
                else_=func.least(VehicleCurrentState.position_sample_count + 1, 3),
            ),
            "map_match_status": "collecting",
            "low_speed_since": case(
                (
                    or_(
                        statement.excluded.speed_kmh.is_(None),
                        statement.excluded.speed_kmh >= 1,
                    ),
                    None,
                ),
                (
                    window_must_reset,
                    func.coalesce(
                        statement.excluded.source_timestamp,
                        statement.excluded.received_at,
                    ),
                ),
                (
                    and_(
                        VehicleCurrentState.speed_kmh.is_not(None),
                        VehicleCurrentState.speed_kmh < 1,
                    ),
                    func.coalesce(
                        VehicleCurrentState.low_speed_since,
                        VehicleCurrentState.source_timestamp,
                        VehicleCurrentState.received_at,
                    ),
                ),
                else_=func.coalesce(
                    statement.excluded.source_timestamp,
                    statement.excluded.received_at,
                ),
            ),
            "last_boundary_stop_id": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_stop_id,
            ),
            "last_boundary_stop_sequence": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_stop_sequence,
            ),
            "last_boundary_progress_m": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_progress_m,
            ),
            "last_boundary_projection_quality": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_projection_quality,
            ),
            "last_boundary_crossed_at": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_crossed_at,
            ),
            "last_boundary_observation_at": case(
                (window_must_reset, None),
                else_=VehicleCurrentState.last_boundary_observation_at,
            ),
        }
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[VehicleCurrentState.vehicle_prefix],
            set_=update_columns,
            where=incoming_is_newer,
        )
    )


async def _project_correlated_vehicles(
    session: AsyncSession,
    *,
    ingestion_run_id: object,
    projected_at: datetime,
) -> None:
    await session.execute(
        text(
            """
            UPDATE realtime.vehicle_current_states AS vehicle
            SET
                shape_position = ST_LineLocatePoint(shape.geometry, vehicle.location),
                projected_location = ST_ClosestPoint(shape.geometry, vehicle.location),
                distance_to_shape_m = ST_Distance(
                    vehicle.location::geography,
                    ST_ClosestPoint(shape.geometry, vehicle.location)::geography
                ),
                projected_at = :projected_at,
                projection_quality = CASE
                    WHEN ST_Distance(
                        vehicle.location::geography,
                        ST_ClosestPoint(shape.geometry, vehicle.location)::geography
                    ) <= 30 THEN 'valid'
                    WHEN ST_Distance(
                        vehicle.location::geography,
                        ST_ClosestPoint(shape.geometry, vehicle.location)::geography
                    ) <= 50 THEN 'reduced'
                    ELSE 'fallback_required'
                END,
                map_match_status = CASE
                    WHEN ST_Distance(
                        vehicle.location::geography,
                        ST_ClosestPoint(shape.geometry, vehicle.location)::geography
                    ) > 50 THEN 'fallback_required'
                    WHEN vehicle.position_sample_count < 3 THEN 'collecting'
                    ELSE 'ambiguous'
                END
            FROM core.gtfs_shapes AS shape
            WHERE vehicle.ingestion_run_id = :ingestion_run_id
              AND vehicle.feed_id = shape.feed_id
              AND vehicle.shape_id = shape.shape_id
              AND vehicle.location IS NOT NULL
            """
        ),
        {"ingestion_run_id": ingestion_run_id, "projected_at": projected_at},
    )


async def _temporally_match_correlated_vehicles(
    session: AsyncSession,
    *,
    ingestion_run_id: object,
    projected_at: datetime,
) -> None:
    candidate_rows = await session.execute(
        text(
            """
            WITH vehicle_samples AS (
                SELECT
                    vehicle.vehicle_prefix,
                    0 AS sample_index,
                    vehicle.feed_id,
                    vehicle.shape_id,
                    vehicle.source_timestamp AS sample_timestamp,
                    vehicle.latitude AS sample_latitude,
                    vehicle.longitude AS sample_longitude,
                    vehicle.location AS sample_location
                FROM realtime.vehicle_current_states AS vehicle
                WHERE vehicle.ingestion_run_id = :ingestion_run_id
                  AND vehicle.correlation_status = 'matched'
                  AND vehicle.location IS NOT NULL

                UNION ALL

                SELECT
                    vehicle.vehicle_prefix,
                    previous.sample_index,
                    vehicle.feed_id,
                    vehicle.shape_id,
                    (previous.state->>'source_timestamp')::timestamptz,
                    (previous.state->>'latitude')::double precision,
                    (previous.state->>'longitude')::double precision,
                    ST_SetSRID(
                        ST_MakePoint(
                            (previous.state->>'longitude')::double precision,
                            (previous.state->>'latitude')::double precision
                        ),
                        4326
                    )
                FROM realtime.vehicle_current_states AS vehicle
                CROSS JOIN LATERAL (
                    VALUES
                        (1, vehicle.previous_state_1),
                        (2, vehicle.previous_state_2)
                ) AS previous(sample_index, state)
                WHERE vehicle.ingestion_run_id = :ingestion_run_id
                  AND vehicle.correlation_status = 'matched'
                  AND previous.state IS NOT NULL
                  AND previous.state->>'source_timestamp' IS NOT NULL
                  AND previous.state->>'latitude' IS NOT NULL
                  AND previous.state->>'longitude' IS NOT NULL
            )
            SELECT
                sample.vehicle_prefix,
                sample.sample_index,
                sample.sample_timestamp,
                sample.sample_latitude,
                sample.sample_longitude,
                candidate.segment_sequence,
                candidate.progress_m,
                candidate.shape_position,
                candidate.distance_to_shape_m,
                candidate.bearing_degrees,
                candidate.projected_latitude,
                candidate.projected_longitude
            FROM vehicle_samples AS sample
            LEFT JOIN LATERAL (
                SELECT
                    segment.segment_sequence,
                    segment.start_distance_m
                        + ST_LineLocatePoint(segment.geometry, sample.sample_location)
                        * segment.segment_length_m AS progress_m,
                    segment.start_fraction
                        + ST_LineLocatePoint(segment.geometry, sample.sample_location)
                        * (segment.end_fraction - segment.start_fraction) AS shape_position,
                    ST_Distance(
                        segment.geometry::geography,
                        sample.sample_location::geography
                    ) AS distance_to_shape_m,
                    segment.bearing_degrees,
                    ST_Y(ST_ClosestPoint(segment.geometry, sample.sample_location))
                        AS projected_latitude,
                    ST_X(ST_ClosestPoint(segment.geometry, sample.sample_location))
                        AS projected_longitude
                FROM core.gtfs_shape_segments AS segment
                WHERE segment.feed_id = sample.feed_id
                  AND segment.shape_id = sample.shape_id
                  AND segment.geometry && ST_Expand(sample.sample_location, 0.001)
                  AND ST_DWithin(
                      segment.geometry::geography,
                      sample.sample_location::geography,
                      50
                  )
            ) AS candidate ON true
            ORDER BY sample.vehicle_prefix, sample.sample_index, candidate.progress_m
            """
        ),
        {"ingestion_run_id": ingestion_run_id},
    )

    samples_by_vehicle: dict[str, dict[int, dict[str, Any]]] = {}
    for row in candidate_rows.mappings():
        vehicle_samples = samples_by_vehicle.setdefault(row["vehicle_prefix"], {})
        sample = vehicle_samples.setdefault(
            row["sample_index"],
            {
                "timestamp": row["sample_timestamp"],
                "latitude": row["sample_latitude"],
                "longitude": row["sample_longitude"],
                "candidates": [],
            },
        )
        if row["segment_sequence"] is not None:
            sample["candidates"].append(
                ShapeCandidate(
                    segment_sequence=row["segment_sequence"],
                    progress_m=row["progress_m"],
                    shape_position=row["shape_position"],
                    distance_to_shape_m=row["distance_to_shape_m"],
                    bearing_degrees=row["bearing_degrees"],
                    projected_latitude=row["projected_latitude"],
                    projected_longitude=row["projected_longitude"],
                )
            )

    updates: list[dict[str, Any]] = []
    for vehicle_prefix, indexed_samples in samples_by_vehicle.items():
        ordered_samples = tuple(
            PositionSample(
                timestamp=sample["timestamp"],
                latitude=sample["latitude"],
                longitude=sample["longitude"],
                candidates=tuple(sample["candidates"]),
            )
            for _, sample in sorted(indexed_samples.items(), reverse=True)
            if sample["timestamp"] is not None
        )
        result = match_three_samples(ordered_samples)
        selected = result.candidate
        updates.append(
            {
                "vehicle_prefix": vehicle_prefix,
                "ingestion_run_id": ingestion_run_id,
                "map_match_status": result.status,
                "has_candidate": selected is not None,
                "shape_position": selected.shape_position if selected else None,
                "shape_progress_m": selected.progress_m if selected else None,
                "distance_to_shape_m": selected.distance_to_shape_m if selected else None,
                "previous_1_shape_position": (result.path[-2].shape_position if selected else None),
                "previous_1_shape_progress_m": (result.path[-2].progress_m if selected else None),
                "previous_2_shape_position": (result.path[-3].shape_position if selected else None),
                "previous_2_shape_progress_m": (result.path[-3].progress_m if selected else None),
                "projected_latitude": selected.projected_latitude if selected else None,
                "projected_longitude": selected.projected_longitude if selected else None,
                "projection_quality": (
                    "valid"
                    if selected and selected.distance_to_shape_m <= 30
                    else "reduced"
                    if selected
                    else None
                ),
                "projected_at": projected_at,
            }
        )

    if updates:
        await session.execute(
            text(
                """
                UPDATE realtime.vehicle_current_states
                SET
                    map_match_status = :map_match_status,
                    shape_position = CASE
                        WHEN :has_candidate THEN :shape_position
                        ELSE shape_position
                    END,
                    shape_progress_m = CASE
                        WHEN :has_candidate THEN :shape_progress_m
                        ELSE shape_progress_m
                    END,
                    distance_to_shape_m = CASE
                        WHEN :has_candidate THEN :distance_to_shape_m
                        ELSE distance_to_shape_m
                    END,
                    projected_location = CASE
                        WHEN :has_candidate THEN ST_SetSRID(
                            ST_MakePoint(:projected_longitude, :projected_latitude),
                            4326
                        )
                        ELSE projected_location
                    END,
                    projection_quality = CASE
                        WHEN :has_candidate THEN :projection_quality
                        ELSE projection_quality
                    END,
                    projected_at = CASE
                        WHEN :has_candidate THEN :projected_at
                        ELSE projected_at
                    END,
                    previous_state_1 = CASE
                        WHEN :has_candidate THEN
                            jsonb_set(
                                jsonb_set(
                                    jsonb_set(
                                        previous_state_1,
                                        '{shape_position}',
                                        to_jsonb(CAST(
                                            :previous_1_shape_position AS double precision
                                        ))
                                    ),
                                    '{shape_progress_m}',
                                    to_jsonb(CAST(:previous_1_shape_progress_m AS double precision))
                                ),
                                '{map_match_status}',
                                '"resolved"'::jsonb
                            )
                        ELSE previous_state_1
                    END,
                    previous_state_2 = CASE
                        WHEN :has_candidate THEN
                            jsonb_set(
                                jsonb_set(
                                    jsonb_set(
                                        previous_state_2,
                                        '{shape_position}',
                                        to_jsonb(CAST(
                                            :previous_2_shape_position AS double precision
                                        ))
                                    ),
                                    '{shape_progress_m}',
                                    to_jsonb(CAST(:previous_2_shape_progress_m AS double precision))
                                ),
                                '{map_match_status}',
                                '"resolved"'::jsonb
                            )
                        ELSE previous_state_2
                    END
                WHERE vehicle_prefix = :vehicle_prefix
                  AND ingestion_run_id = :ingestion_run_id
                """
            ),
            updates,
        )


async def _identify_current_segments(
    session: AsyncSession,
    *,
    ingestion_run_id: object,
) -> None:
    await session.execute(
        text(
            """
            WITH located_segments AS (
                SELECT
                    vehicle.vehicle_prefix,
                    segment.origin_stop_id,
                    segment.destination_stop_id,
                    segment.origin_stop_sequence,
                    segment.destination_stop_sequence
                FROM realtime.vehicle_current_states AS vehicle
                JOIN LATERAL (
                    SELECT
                        origin.stop_id AS origin_stop_id,
                        destination.stop_id AS destination_stop_id,
                        origin.stop_sequence AS origin_stop_sequence,
                        destination.stop_sequence AS destination_stop_sequence
                    FROM core.gtfs_stop_times AS origin
                    JOIN LATERAL (
                        SELECT candidate.stop_id, candidate.stop_sequence,
                               candidate.shape_position,
                               candidate.shape_projection_quality
                        FROM core.gtfs_stop_times AS candidate
                        WHERE candidate.feed_id = origin.feed_id
                          AND candidate.trip_id = origin.trip_id
                          AND candidate.stop_sequence > origin.stop_sequence
                        ORDER BY candidate.stop_sequence
                        LIMIT 1
                    ) AS destination ON true
                    WHERE origin.feed_id = vehicle.feed_id
                      AND origin.trip_id = vehicle.trip_id
                      AND origin.shape_projection_quality IN ('valid', 'reduced')
                      AND destination.shape_projection_quality IN ('valid', 'reduced')
                      AND origin.shape_position IS NOT NULL
                      AND destination.shape_position IS NOT NULL
                      AND origin.shape_position <= vehicle.shape_position
                      AND destination.shape_position > vehicle.shape_position
                    ORDER BY origin.shape_position DESC, origin.stop_sequence DESC
                    LIMIT 1
                ) AS segment ON true
                WHERE vehicle.ingestion_run_id = :ingestion_run_id
                  AND vehicle.map_match_status = 'resolved'
            )
            UPDATE realtime.vehicle_current_states AS vehicle
            SET
                current_origin_stop_id = segment.origin_stop_id,
                current_destination_stop_id = segment.destination_stop_id,
                current_origin_stop_sequence = segment.origin_stop_sequence,
                current_destination_stop_sequence = segment.destination_stop_sequence
            FROM located_segments AS segment
            WHERE vehicle.vehicle_prefix = segment.vehicle_prefix
            """
        ),
        {"ingestion_run_id": ingestion_run_id},
    )


async def _refresh_live_segment_metrics(
    session: AsyncSession,
    observations: list[dict[str, Any]],
) -> MetricRefreshResult:
    target_windows = {
        observation["metric_key"]: five_minute_window(observation["completed_at"])[0]
        for observation in observations
    }
    earliest_window = min(target_windows.values())
    latest_window_end = max(
        five_minute_window(observation["completed_at"])[1] for observation in observations
    )
    result = await session.execute(
        text(
            """
            SELECT
                metric_key, scope, origin_stop_id, destination_stop_id,
                route_id, direction_id, source_feed_id, completed_at,
                duration_seconds, accepted, weight
            FROM analytics.segment_completion_observations
            WHERE metric_key = ANY(CAST(:metric_keys AS text[]))
              AND completed_at >= :earliest_window
              AND completed_at < :latest_window_end
            ORDER BY metric_key, completed_at
            """
        ),
        {
            "metric_keys": list(target_windows),
            "earliest_window": earliest_window,
            "latest_window_end": latest_window_end,
        },
    )

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in result.mappings():
        if five_minute_window(row["completed_at"])[0] == target_windows[row["metric_key"]]:
            groups.setdefault(row["metric_key"], []).append(row)

    updated_at = datetime.now(UTC)
    metrics: list[dict[str, Any]] = []
    for metric_key, rows in groups.items():
        statistics_ = aggregate_window(
            [
                SegmentCompletionSample(
                    completed_at=row["completed_at"],
                    duration_seconds=row["duration_seconds"],
                    accepted=row["accepted"],
                    weight=row["weight"],
                )
                for row in rows
            ]
        )
        latest_row = max(rows, key=lambda row: row["completed_at"])
        day_type, slot_index = profile_slot(statistics_.window_start)
        metrics.append(
            {
                "metric_key": metric_key,
                "scope": latest_row["scope"],
                "origin_stop_id": latest_row["origin_stop_id"],
                "destination_stop_id": latest_row["destination_stop_id"],
                "route_id": latest_row["route_id"],
                "direction_id": latest_row["direction_id"],
                "source_feed_id": latest_row["source_feed_id"],
                "window_start": statistics_.window_start,
                "window_end": statistics_.window_end,
                "service_date": statistics_.window_start.date(),
                "day_type": day_type,
                "slot_index": slot_index,
                "sample_count_total": statistics_.sample_count_total,
                "sample_count_accepted": statistics_.sample_count_accepted,
                "sample_count_rejected": statistics_.sample_count_rejected,
                "accepted_weight": statistics_.accepted_weight,
                "mean_seconds": statistics_.mean_seconds,
                "median_seconds": statistics_.median_seconds,
                "standard_deviation_seconds": (statistics_.standard_deviation_seconds),
                "minimum_seconds": statistics_.minimum_seconds,
                "maximum_seconds": statistics_.maximum_seconds,
                "m2_seconds": statistics_.m2_seconds,
                "reliability": metric_reliability(statistics_),
                "status": metric_status(statistics_),
                "last_completed_at": statistics_.last_completed_at,
                "updated_at": updated_at,
            }
        )

    if metrics:
        await session.execute(
            text(
                """
                INSERT INTO analytics.segment_live_metrics_5m (
                    metric_key, scope, origin_stop_id, destination_stop_id,
                    route_id, direction_id, source_feed_id, window_start,
                    window_end, sample_count_total, sample_count_accepted,
                    sample_count_rejected, accepted_weight, mean_seconds,
                    median_seconds, standard_deviation_seconds, minimum_seconds,
                    maximum_seconds, reliability, status, last_completed_at,
                    updated_at
                ) VALUES (
                    :metric_key, :scope, :origin_stop_id, :destination_stop_id,
                    :route_id, :direction_id, :source_feed_id, :window_start,
                    :window_end, :sample_count_total, :sample_count_accepted,
                    :sample_count_rejected, :accepted_weight, :mean_seconds,
                    :median_seconds, :standard_deviation_seconds,
                    :minimum_seconds, :maximum_seconds, :reliability, :status,
                    :last_completed_at, :updated_at
                )
                ON CONFLICT (metric_key) DO UPDATE SET
                    scope = EXCLUDED.scope,
                    origin_stop_id = EXCLUDED.origin_stop_id,
                    destination_stop_id = EXCLUDED.destination_stop_id,
                    route_id = EXCLUDED.route_id,
                    direction_id = EXCLUDED.direction_id,
                    source_feed_id = EXCLUDED.source_feed_id,
                    window_start = EXCLUDED.window_start,
                    window_end = EXCLUDED.window_end,
                    sample_count_total = EXCLUDED.sample_count_total,
                    sample_count_accepted = EXCLUDED.sample_count_accepted,
                    sample_count_rejected = EXCLUDED.sample_count_rejected,
                    accepted_weight = EXCLUDED.accepted_weight,
                    mean_seconds = EXCLUDED.mean_seconds,
                    median_seconds = EXCLUDED.median_seconds,
                    standard_deviation_seconds = EXCLUDED.standard_deviation_seconds,
                    minimum_seconds = EXCLUDED.minimum_seconds,
                    maximum_seconds = EXCLUDED.maximum_seconds,
                    reliability = EXCLUDED.reliability,
                    status = EXCLUDED.status,
                    last_completed_at = EXCLUDED.last_completed_at,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            metrics,
        )

        await session.execute(
            text(
                """
                INSERT INTO analytics.segment_daily_metrics_5m (
                    metric_key, service_date, slot_index, day_type, scope,
                    origin_stop_id, destination_stop_id, route_id, direction_id,
                    source_feed_id, sample_count_total, sample_count_accepted,
                    sample_count_rejected, accepted_weight, mean_seconds,
                    median_seconds, standard_deviation_seconds, minimum_seconds,
                    maximum_seconds, m2_seconds, reliability, last_completed_at,
                    updated_at
                ) VALUES (
                    :metric_key, :service_date, :slot_index, :day_type, :scope,
                    :origin_stop_id, :destination_stop_id, :route_id,
                    :direction_id, :source_feed_id, :sample_count_total,
                    :sample_count_accepted, :sample_count_rejected,
                    :accepted_weight, :mean_seconds, :median_seconds,
                    :standard_deviation_seconds, :minimum_seconds,
                    :maximum_seconds, :m2_seconds, :reliability,
                    :last_completed_at, :updated_at
                )
                ON CONFLICT (metric_key, service_date, slot_index) DO UPDATE SET
                    day_type = EXCLUDED.day_type,
                    scope = EXCLUDED.scope,
                    origin_stop_id = EXCLUDED.origin_stop_id,
                    destination_stop_id = EXCLUDED.destination_stop_id,
                    route_id = EXCLUDED.route_id,
                    direction_id = EXCLUDED.direction_id,
                    source_feed_id = EXCLUDED.source_feed_id,
                    sample_count_total = EXCLUDED.sample_count_total,
                    sample_count_accepted = EXCLUDED.sample_count_accepted,
                    sample_count_rejected = EXCLUDED.sample_count_rejected,
                    accepted_weight = EXCLUDED.accepted_weight,
                    mean_seconds = EXCLUDED.mean_seconds,
                    median_seconds = EXCLUDED.median_seconds,
                    standard_deviation_seconds = EXCLUDED.standard_deviation_seconds,
                    minimum_seconds = EXCLUDED.minimum_seconds,
                    maximum_seconds = EXCLUDED.maximum_seconds,
                    m2_seconds = EXCLUDED.m2_seconds,
                    reliability = EXCLUDED.reliability,
                    last_completed_at = EXCLUDED.last_completed_at,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            metrics,
        )
    return MetricRefreshResult(
        live_metrics_updated=len(metrics),
        daily_metrics_updated=len(metrics),
    )


async def _recover_unmaterialized_metric_windows(
    session: AsyncSession,
) -> MetricRefreshResult:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT ON (observation.metric_key)
                observation.metric_key,
                observation.completed_at
            FROM analytics.segment_completion_observations AS observation
            WHERE observation.expires_at > CURRENT_TIMESTAMP
              AND NOT EXISTS (
                  SELECT 1
                  FROM analytics.segment_daily_metrics_5m AS daily
                  WHERE daily.metric_key = observation.metric_key
                    AND daily.service_date = (
                        observation.completed_at
                        AT TIME ZONE 'America/Sao_Paulo'
                    )::date
                    AND daily.slot_index = (
                        EXTRACT(HOUR FROM observation.completed_at
                            AT TIME ZONE 'America/Sao_Paulo')::integer * 12
                        + FLOOR(EXTRACT(MINUTE FROM observation.completed_at
                            AT TIME ZONE 'America/Sao_Paulo') / 5)::integer
                    )
              )
            ORDER BY observation.metric_key, observation.completed_at DESC
            """
        )
    )
    windows = [
        {"metric_key": row["metric_key"], "completed_at": row["completed_at"]}
        for row in result.mappings()
    ]
    if not windows:
        return MetricRefreshResult(0, 0)
    return await _refresh_live_segment_metrics(session, windows)


async def _process_boundary_crossings(
    session: AsyncSession,
    *,
    ingestion_run_id: object,
    service_date: date,
) -> BoundaryProcessingResult:
    await session.execute(
        text(
            "DELETE FROM analytics.segment_completion_observations "
            "WHERE expires_at <= CURRENT_TIMESTAMP"
        )
    )
    await session.execute(
        text(
            "DELETE FROM analytics.segment_daily_metrics_5m "
            "WHERE service_date < :oldest_service_date"
        ),
        {"oldest_service_date": historical_retention_start(service_date)},
    )
    result = await session.execute(
        text(
            """
            WITH relevant_trips AS (
                SELECT DISTINCT vehicle.feed_id, vehicle.trip_id
                FROM realtime.vehicle_current_states AS vehicle
                WHERE vehicle.ingestion_run_id = :ingestion_run_id
                  AND vehicle.map_match_status = 'resolved'
                  AND vehicle.feed_id IS NOT NULL
                  AND vehicle.trip_id IS NOT NULL
            ),
            ordered_boundaries AS (
                SELECT
                    stop_time.feed_id,
                    stop_time.trip_id,
                    stop_time.stop_id,
                    stop_time.stop_sequence,
                    lag(stop_time.stop_sequence) OVER (
                        PARTITION BY stop_time.feed_id, stop_time.trip_id
                        ORDER BY stop_time.stop_sequence
                    ) AS previous_stop_sequence,
                    stop_time.shape_progress_m,
                    stop_time.shape_projection_quality
                FROM core.gtfs_stop_times AS stop_time
                JOIN relevant_trips AS trip
                  ON trip.feed_id = stop_time.feed_id
                 AND trip.trip_id = stop_time.trip_id
            )
            SELECT
                vehicle.vehicle_prefix,
                vehicle.feed_id,
                vehicle.route_id,
                trip.direction_id,
                vehicle.source_timestamp AS current_timestamp,
                vehicle.shape_progress_m AS current_progress_m,
                (vehicle.previous_state_1->>'source_timestamp')::timestamptz
                    AS previous_timestamp,
                (vehicle.previous_state_1->>'shape_progress_m')::double precision
                    AS previous_progress_m,
                vehicle.last_boundary_stop_id,
                vehicle.last_boundary_stop_sequence,
                vehicle.last_boundary_progress_m,
                vehicle.last_boundary_projection_quality,
                vehicle.last_boundary_crossed_at,
                vehicle.last_boundary_observation_at,
                boundary.stop_id AS boundary_stop_id,
                boundary.stop_sequence AS boundary_stop_sequence,
                boundary.previous_stop_sequence AS boundary_previous_stop_sequence,
                boundary.shape_progress_m AS boundary_progress_m,
                boundary.shape_projection_quality AS boundary_projection_quality
            FROM realtime.vehicle_current_states AS vehicle
            JOIN core.gtfs_trips AS trip
              ON trip.feed_id = vehicle.feed_id
             AND trip.trip_id = vehicle.trip_id
            JOIN LATERAL (
                SELECT boundary.*
                FROM ordered_boundaries AS boundary
                WHERE boundary.feed_id = vehicle.feed_id
                  AND boundary.trip_id = vehicle.trip_id
                  AND boundary.shape_progress_m >
                      (vehicle.previous_state_1->>'shape_progress_m')::double precision
                  AND boundary.shape_progress_m <= vehicle.shape_progress_m
                ORDER BY boundary.shape_progress_m, boundary.stop_sequence
            ) AS boundary ON true
            WHERE vehicle.ingestion_run_id = :ingestion_run_id
              AND vehicle.map_match_status = 'resolved'
              AND vehicle.source_timestamp IS NOT NULL
              AND vehicle.shape_progress_m IS NOT NULL
              AND vehicle.previous_state_1->>'map_match_status' = 'resolved'
              AND vehicle.previous_state_1->>'source_timestamp' IS NOT NULL
              AND vehicle.previous_state_1->>'shape_progress_m' IS NOT NULL
            ORDER BY vehicle.vehicle_prefix, boundary.shape_progress_m,
                     boundary.stop_sequence
            """
        ),
        {"ingestion_run_id": ingestion_run_id},
    )

    vehicles: dict[str, dict[str, Any]] = {}
    for row in result.mappings():
        vehicle = vehicles.setdefault(
            row["vehicle_prefix"],
            {
                "current_timestamp": row["current_timestamp"],
                "current_progress_m": row["current_progress_m"],
                "feed_id": row["feed_id"],
                "route_id": row["route_id"],
                "direction_id": row["direction_id"],
                "previous_timestamp": row["previous_timestamp"],
                "previous_progress_m": row["previous_progress_m"],
                "last_boundary": (
                    BoundaryCrossing(
                        stop_id=row["last_boundary_stop_id"],
                        stop_sequence=row["last_boundary_stop_sequence"],
                        previous_stop_sequence=None,
                        progress_m=row["last_boundary_progress_m"],
                        projection_quality=row["last_boundary_projection_quality"],
                        crossed_at=row["last_boundary_crossed_at"],
                        observation_end=row["last_boundary_observation_at"],
                    )
                    if row["last_boundary_stop_id"] is not None
                    and row["last_boundary_stop_sequence"] is not None
                    and row["last_boundary_progress_m"] is not None
                    and row["last_boundary_projection_quality"] is not None
                    and row["last_boundary_crossed_at"] is not None
                    and row["last_boundary_observation_at"] is not None
                    else None
                ),
                "boundaries": [],
            },
        )
        vehicle["boundaries"].append(
            SegmentBoundary(
                stop_id=row["boundary_stop_id"],
                stop_sequence=row["boundary_stop_sequence"],
                previous_stop_sequence=row["boundary_previous_stop_sequence"],
                progress_m=row["boundary_progress_m"],
                projection_quality=row["boundary_projection_quality"],
            )
        )

    updates: list[dict[str, Any]] = []
    crossing_count = 0
    completed_high = 0
    completed_reduced = 0
    pending_observations: list[dict[str, Any]] = []
    for vehicle_prefix, vehicle in vehicles.items():
        crossings = interpolate_crossed_boundaries(
            previous_timestamp=vehicle["previous_timestamp"],
            current_timestamp=vehicle["current_timestamp"],
            previous_progress_m=vehicle["previous_progress_m"],
            current_progress_m=vehicle["current_progress_m"],
            boundaries=tuple(vehicle["boundaries"]),
        )
        completed, last_boundary = complete_segments_from_crossings(
            last_boundary=vehicle["last_boundary"],
            crossings=crossings,
        )
        crossing_count += len(crossings)
        completed_high += sum(item.confidence == "high" for item in completed)
        completed_reduced += sum(item.confidence == "reduced" for item in completed)
        if vehicle["route_id"] is not None and vehicle["direction_id"] is not None:
            for segment in completed:
                for identity in metric_identities_for_segment(
                    origin_stop_id=segment.origin_stop_id,
                    destination_stop_id=segment.destination_stop_id,
                    route_id=vehicle["route_id"],
                    direction_id=vehicle["direction_id"],
                ):
                    pending_observations.append(
                        {
                            "metric_key": identity.metric_key,
                            "scope": identity.scope,
                            "origin_stop_id": identity.origin_stop_id,
                            "destination_stop_id": identity.destination_stop_id,
                            "route_id": identity.route_id,
                            "direction_id": identity.direction_id,
                            "source_feed_id": vehicle["feed_id"],
                            "completed_at": segment.completed_at,
                            "expires_at": segment.completed_at + timedelta(hours=1),
                            "duration_seconds": segment.duration_seconds,
                            "distance_m": segment.distance_m,
                            "average_speed_kmh": segment.average_speed_kmh,
                            "confidence": segment.confidence,
                        }
                    )
        if last_boundary is not None:
            updates.append(
                {
                    "vehicle_prefix": vehicle_prefix,
                    "ingestion_run_id": ingestion_run_id,
                    "stop_id": last_boundary.stop_id,
                    "stop_sequence": last_boundary.stop_sequence,
                    "progress_m": last_boundary.progress_m,
                    "projection_quality": last_boundary.projection_quality,
                    "crossed_at": last_boundary.crossed_at,
                    "observation_at": last_boundary.observation_end,
                }
            )

    if updates:
        await session.execute(
            text(
                """
                UPDATE realtime.vehicle_current_states
                SET
                    last_boundary_stop_id = :stop_id,
                    last_boundary_stop_sequence = :stop_sequence,
                    last_boundary_progress_m = :progress_m,
                    last_boundary_projection_quality = :projection_quality,
                    last_boundary_crossed_at = :crossed_at,
                    last_boundary_observation_at = :observation_at
                WHERE vehicle_prefix = :vehicle_prefix
                  AND ingestion_run_id = :ingestion_run_id
                """
            ),
            updates,
        )

    accepted_count = 0
    rejected_speed = 0
    rejected_mad = 0
    live_metrics_updated = 0
    daily_metrics_updated = 0
    if pending_observations:
        reference_result = await session.execute(
            text(
                """
                SELECT metric_key, duration_seconds
                FROM analytics.segment_completion_observations
                WHERE metric_key = ANY(CAST(:metric_keys AS text[]))
                  AND accepted
                  AND completed_at > CURRENT_TIMESTAMP - INTERVAL '1 hour'
                  AND expires_at > CURRENT_TIMESTAMP
                ORDER BY completed_at
                """
            ),
            {"metric_keys": list({item["metric_key"] for item in pending_observations})},
        )
        references: dict[str, list[float]] = {}
        for row in reference_result.mappings():
            references.setdefault(row["metric_key"], []).append(row["duration_seconds"])

        created_at = datetime.now(UTC)
        assessed_observations: list[dict[str, Any]] = []
        for observation in sorted(
            pending_observations,
            key=lambda item: (item["completed_at"], item["metric_key"]),
        ):
            metric_references = references.setdefault(observation["metric_key"], [])
            assessment = assess_segment_sample(
                duration_seconds=observation["duration_seconds"],
                distance_m=observation["distance_m"],
                confidence=observation["confidence"],
                accepted_reference_durations=tuple(metric_references),
            )
            assessed = {
                **observation,
                "weight": assessment.weight,
                "accepted": assessment.accepted,
                "rejection_reason": assessment.rejection_reason,
                "created_at": created_at,
            }
            assessed_observations.append(assessed)
            if assessment.accepted:
                accepted_count += 1
                metric_references.append(observation["duration_seconds"])
            elif assessment.rejection_reason == "speed_over_80":
                rejected_speed += 1
            elif assessment.rejection_reason == "mad_outlier":
                rejected_mad += 1

        await session.execute(
            text(
                """
                INSERT INTO analytics.segment_completion_observations (
                    id, metric_key, scope, origin_stop_id, destination_stop_id,
                    route_id, direction_id, source_feed_id, completed_at,
                    expires_at, duration_seconds, distance_m, average_speed_kmh,
                    confidence, weight, accepted, rejection_reason, created_at
                ) VALUES (
                    gen_random_uuid(), :metric_key, :scope, :origin_stop_id,
                    :destination_stop_id, :route_id, :direction_id,
                    :source_feed_id, :completed_at, :expires_at,
                    :duration_seconds, :distance_m, :average_speed_kmh,
                    :confidence, :weight, :accepted, :rejection_reason,
                    :created_at
                )
                """
            ),
            assessed_observations,
        )
        metric_refresh = await _refresh_live_segment_metrics(
            session,
            assessed_observations,
        )
        live_metrics_updated = metric_refresh.live_metrics_updated
        daily_metrics_updated = metric_refresh.daily_metrics_updated
    else:
        metric_refresh = await _recover_unmaterialized_metric_windows(session)
        live_metrics_updated = metric_refresh.live_metrics_updated
        daily_metrics_updated = metric_refresh.daily_metrics_updated

    return BoundaryProcessingResult(
        crossing_count=crossing_count,
        completed_high_confidence=completed_high,
        completed_reduced_confidence=completed_reduced,
        observations_written=len(pending_observations),
        observations_accepted=accepted_count,
        rejected_speed=rejected_speed,
        rejected_mad=rejected_mad,
        live_metrics_updated=live_metrics_updated,
        daily_metrics_updated=daily_metrics_updated,
    )


async def ingest_cittati_vehicles(
    session: AsyncSession,
    source: CittatiVehicleSource,
    *,
    active_trip_index: ActiveTripIndex | None = None,
) -> IngestionRun:
    run = IngestionRun(
        source_system="cittati",
        resource_name="operacional/veiculos",
        status="running",
        run_metadata={"model": 4, "storage_mode": "current_state_only"},
    )
    session.add(run)
    await session.flush()

    try:
        response = await source.fetch_vehicles(model=4)
    except Exception as error:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_message = f"{type(error).__name__}: {error}"
        await session.commit()
        raise

    record_count = count_vehicle_records(response.payload)
    run.records_received = record_count
    run.records_written = 0
    run.http_status = response.http_status

    if not is_successful_vehicle_response(response):
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_message = "Cittati vehicle response did not contain campos and dados arrays."
        run.run_metadata = {
            "model": 4,
            "storage_mode": "current_state_only",
            "payload_hash": response.payload_hash,
        }
        await session.commit()
        return run

    assert isinstance(response.payload, dict)
    batch = parse_vehicle_batch(
        response.payload,
        ingestion_run_id=run.id,
        payload_hash=response.payload_hash,
        received_at=response.received_at,
    )
    service_date = response.received_at.astimezone(_OPERATIONAL_TIMEZONE).date()
    trip_index = active_trip_index
    if trip_index is None:
        trip_index = await load_active_trip_index(session, service_date=service_date)
    apply_exact_trip_correlations(batch.rows, trip_index)
    await _upsert_current_states(session, batch.rows)
    await _project_correlated_vehicles(
        session,
        ingestion_run_id=run.id,
        projected_at=response.received_at,
    )
    await _temporally_match_correlated_vehicles(
        session,
        ingestion_run_id=run.id,
        projected_at=response.received_at,
    )
    boundary_result = await _process_boundary_crossings(
        session,
        ingestion_run_id=run.id,
        service_date=service_date,
    )
    profile_refresh = await refresh_historical_profiles_if_due(
        session,
        current_service_date=service_date,
    )
    await _identify_current_segments(session, ingestion_run_id=run.id)

    run.status = "partial" if batch.rejected_count else "succeeded"
    run.finished_at = datetime.now(UTC)
    run.records_written = len(batch.rows)
    run.run_metadata = {
        "model": 4,
        "storage_mode": "current_state_only",
        "payload_hash": response.payload_hash,
        "field_names": response.payload.get("campos", []),
        "records_rejected": batch.rejected_count,
        "duplicate_prefixes": batch.duplicate_prefix_count,
        "invalid_locations": batch.invalid_location_count,
        "invalid_timestamps": batch.invalid_timestamp_count,
        "boundary_crossings": boundary_result.crossing_count,
        "completed_segments_high_confidence": (boundary_result.completed_high_confidence),
        "completed_segments_reduced_confidence": (boundary_result.completed_reduced_confidence),
        "segment_observations_written": boundary_result.observations_written,
        "segment_observations_accepted": boundary_result.observations_accepted,
        "segment_observations_rejected_speed": boundary_result.rejected_speed,
        "segment_observations_rejected_mad": boundary_result.rejected_mad,
        "segment_live_metrics_updated": boundary_result.live_metrics_updated,
        "segment_daily_metrics_updated": boundary_result.daily_metrics_updated,
        "historical_profiles_refreshed": profile_refresh.performed,
        "historical_profiles_updated": profile_refresh.profiles_updated,
        "historical_reference_start_date": (profile_refresh.reference_start_date.isoformat()),
        "historical_reference_end_date": (profile_refresh.reference_end_date.isoformat()),
    }

    await session.commit()
    return run
