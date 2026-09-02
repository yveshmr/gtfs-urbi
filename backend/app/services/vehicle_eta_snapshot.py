from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle_state import VehicleEtaSnapshot
from app.schemas.vehicle_eta import (
    VehicleEtaSnapshotListResponse,
    VehicleEtaSnapshotResponse,
    build_vehicle_eta_response,
)
from app.services.segment_aggregation import five_minute_window
from app.services.segment_estimate_catalog import (
    SegmentEstimateRequest,
    load_fleet_segment_estimate_catalog,
)
from app.services.vehicle_eta_query import (
    VehicleEtaUnavailableError,
    build_remaining_trip_segments,
    compose_vehicle_eta_result,
    validate_vehicle_eta_state,
)

_MAX_SNAPSHOT_AGE = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class VehicleEtaSnapshotRefreshResult:
    performed: bool
    eligible_vehicle_count: int
    snapshot_count: int
    unavailable_vehicle_count: int


async def refresh_vehicle_eta_snapshots(
    session: AsyncSession,
    *,
    queried_at: datetime,
    force: bool = False,
) -> VehicleEtaSnapshotRefreshResult:
    if queried_at.tzinfo is None:
        raise ValueError("Snapshot timestamp must include a timezone.")

    window_start, _ = five_minute_window(queried_at)
    if not force:
        latest_generated_at = await session.scalar(
            select(func.max(VehicleEtaSnapshot.generated_at)).where(
                func.coalesce(
                    VehicleEtaSnapshot.payload["calculation_mode"].as_string(),
                    "enriched",
                )
                == "enriched"
            )
        )
        if latest_generated_at is not None and latest_generated_at >= window_start:
            return VehicleEtaSnapshotRefreshResult(False, 0, 0, 0)

    state_result = await session.execute(
        text(
            """
            SELECT
                vehicle.vehicle_prefix,
                vehicle.source_timestamp,
                vehicle.feed_id,
                vehicle.trip_id,
                vehicle.route_id,
                trip.direction_id,
                vehicle.shape_progress_m,
                vehicle.current_origin_stop_sequence,
                vehicle.current_destination_stop_sequence
            FROM realtime.vehicle_current_states AS vehicle
            JOIN core.gtfs_trips AS trip
              ON trip.feed_id = vehicle.feed_id
             AND trip.trip_id = vehicle.trip_id
            WHERE vehicle.source_timestamp >= :fresh_after
              AND vehicle.shape_progress_m IS NOT NULL
              AND vehicle.current_origin_stop_sequence IS NOT NULL
              AND vehicle.current_destination_stop_sequence IS NOT NULL
            """
        ),
        {"fresh_after": queried_at - timedelta(minutes=5)},
    )
    states = list(state_result.mappings())
    if not states:
        return VehicleEtaSnapshotRefreshResult(True, 0, 0, 0)

    requested_trips = [
        {"feed_id": str(feed_id), "trip_id": trip_id}
        for feed_id, trip_id in dict.fromkeys(
            (state["feed_id"], state["trip_id"]) for state in states
        )
    ]
    stops_result = await session.execute(
        text(
            """
            WITH requested_trips AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:trips AS jsonb)) AS requested(
                    feed_id uuid,
                    trip_id text
                )
            )
            SELECT stop_time.feed_id, stop_time.trip_id, stop_time.stop_id,
                   stop_time.stop_sequence, stop_time.shape_progress_m,
                   stop_time.arrival_seconds, stop_time.departure_seconds
            FROM requested_trips AS requested
            JOIN core.gtfs_stop_times AS stop_time
              ON stop_time.feed_id = requested.feed_id
             AND stop_time.trip_id = requested.trip_id
            ORDER BY stop_time.feed_id, stop_time.trip_id, stop_time.stop_sequence
            """
        ),
        {"trips": json.dumps(requested_trips)},
    )
    stops_by_trip: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for stop in stops_result.mappings():
        stops_by_trip[(stop["feed_id"], stop["trip_id"])].append(stop)

    prepared: list[tuple[dict[str, Any], list[dict[str, Any]], tuple[Any, ...]]] = []
    requests: list[SegmentEstimateRequest] = []
    unavailable = 0
    for state in states:
        trip_stops = stops_by_trip.get((state["feed_id"], state["trip_id"]), [])
        remaining_stops = [
            stop
            for stop in trip_stops
            if stop["stop_sequence"] >= state["current_origin_stop_sequence"]
        ]
        try:
            validate_vehicle_eta_state(state, queried_at=queried_at)
            segments = build_remaining_trip_segments(state, remaining_stops)
        except VehicleEtaUnavailableError:
            unavailable += 1
            continue
        prepared.append((state, remaining_stops, segments))
        requests.extend(
            SegmentEstimateRequest(
                origin_stop_id=segment.origin_stop_id,
                destination_stop_id=segment.destination_stop_id,
                route_id=state["route_id"],
                direction_id=state["direction_id"],
            )
            for segment in segments
        )

    if not prepared:
        return VehicleEtaSnapshotRefreshResult(True, len(states), 0, unavailable)

    catalog = await load_fleet_segment_estimate_catalog(
        session,
        requests=tuple(requests),
        queried_at=queried_at,
    )
    snapshot_rows: list[dict[str, Any]] = []
    for state, stops, segments in prepared:
        result = await compose_vehicle_eta_result(
            state=state,
            stops=stops,
            segments=segments,
            catalog=catalog,
            queried_at=queried_at,
        )
        response = build_vehicle_eta_response(result, queried_at=queried_at)
        snapshot_rows.append(
            {
                "vehicle_prefix": result.vehicle_prefix,
                "source_timestamp": state["source_timestamp"],
                "generated_at": queried_at,
                "trip_id": result.trip_id,
                "route_id": result.route_id,
                "direction_id": result.direction_id,
                "payload": response.model_dump(mode="json"),
            }
        )

    statement = insert(VehicleEtaSnapshot).values(snapshot_rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[VehicleEtaSnapshot.vehicle_prefix],
            set_={
                "source_timestamp": statement.excluded.source_timestamp,
                "generated_at": statement.excluded.generated_at,
                "trip_id": statement.excluded.trip_id,
                "route_id": statement.excluded.route_id,
                "direction_id": statement.excluded.direction_id,
                "payload": statement.excluded.payload,
            },
        )
    )
    return VehicleEtaSnapshotRefreshResult(
        performed=True,
        eligible_vehicle_count=len(states),
        snapshot_count=len(snapshot_rows),
        unavailable_vehicle_count=unavailable,
    )


async def query_vehicle_eta_snapshots(
    session: AsyncSession,
) -> VehicleEtaSnapshotListResponse:
    latest_generated_at = await session.scalar(
        select(func.max(VehicleEtaSnapshot.generated_at))
    )
    if latest_generated_at is None:
        return VehicleEtaSnapshotListResponse(
            generated_at=None,
            count=0,
            vehicles=[],
        )

    result = await session.execute(
        select(VehicleEtaSnapshot.payload, VehicleEtaSnapshot.generated_at)
        .where(VehicleEtaSnapshot.generated_at >= func.now() - _MAX_SNAPSHOT_AGE)
        .order_by(VehicleEtaSnapshot.vehicle_prefix)
    )
    vehicles = [
        VehicleEtaSnapshotResponse(
            **row.payload,
            generated_at=row.generated_at,
        )
        for row in result
    ]
    return VehicleEtaSnapshotListResponse(
        generated_at=latest_generated_at,
        count=len(vehicles),
        vehicles=vehicles,
    )
