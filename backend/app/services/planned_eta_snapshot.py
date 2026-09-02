from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle_state import VehicleEtaSnapshot
from app.schemas.vehicle_eta import build_vehicle_eta_response
from app.services.active_trip_index import ActiveTripCandidate, ActiveTripIndex
from app.services.segment_aggregation import ResolvedSegmentEstimate
from app.services.vehicle_eta import (
    EtaProjection,
    EtaTarget,
    RemainingTripSegment,
    compose_eta_projection,
)
from app.services.vehicle_eta_query import VehicleEtaResult, planned_trip_end_at

_MAX_SNAPSHOT_AGE = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class PlannedEtaSnapshotRefreshResult:
    eligible_vehicle_count: int
    snapshot_count: int
    unavailable_vehicle_count: int


class _PlannedOnlyCatalog:
    def resolve(
        self,
        segment: RemainingTripSegment,
        estimate_at: datetime,
        scope: str,
        *,
        route_id: str,
        direction_id: int,
    ) -> ResolvedSegmentEstimate:
        del estimate_at, scope, route_id, direction_id
        if segment.planned_duration_seconds is None:
            return ResolvedSegmentEstimate(None, 0, 0, "unavailable", None, None)
        return ResolvedSegmentEstimate(
            segment.planned_duration_seconds,
            1.0,
            1,
            "gtfs_planned",
            None,
            None,
        )


def _remaining_segments(
    candidate: ActiveTripCandidate,
    *,
    shape_progress_m: float,
    origin_stop_sequence: int | None,
    destination_stop_sequence: int | None,
) -> tuple[RemainingTripSegment, ...]:
    planned = candidate.planned_segments
    if not planned:
        return ()

    current_index: int | None = None
    if origin_stop_sequence is not None and destination_stop_sequence is not None:
        current_index = next(
            (
                index
                for index, segment in enumerate(planned)
                if segment.origin_stop_sequence == origin_stop_sequence
                and segment.destination_stop_sequence == destination_stop_sequence
            ),
            None,
        )
    if current_index is None:
        current_index = next(
            (
                index
                for index, segment in enumerate(planned)
                if segment.origin_progress_m
                <= shape_progress_m
                < segment.destination_progress_m
            ),
            None,
        )
    if current_index is None and shape_progress_m < planned[0].origin_progress_m:
        current_index = 0
    if current_index is None:
        return ()

    remaining: list[RemainingTripSegment] = []
    for index, segment in enumerate(planned[current_index:]):
        fraction = 1.0
        if index == 0:
            fraction = max(
                0.0,
                min(
                    1.0,
                    (segment.destination_progress_m - shape_progress_m)
                    / (segment.destination_progress_m - segment.origin_progress_m),
                ),
            )
        remaining.append(
            RemainingTripSegment(
                origin_stop_id=segment.origin_stop_id,
                destination_stop_id=segment.destination_stop_id,
                origin_stop_sequence=segment.origin_stop_sequence,
                destination_stop_sequence=segment.destination_stop_sequence,
                remaining_fraction=fraction,
                planned_duration_seconds=segment.duration_seconds,
            )
        )
    return tuple(remaining)


def _arrived_projection(
    *,
    scope: str,
    scenario: str,
    queried_at: datetime,
) -> EtaProjection:
    target = EtaTarget(
        value_seconds=0.0,
        estimated_at=queried_at,
        reliability=1.0,
        segments_covered=0,
        segments_total=0,
        source_counts={"gtfs_planned": 0},
        complete=True,
        missing_origin_stop_id=None,
        missing_destination_stop_id=None,
    )
    return EtaProjection(scope=scope, scenario=scenario, next_stop=target, trip_end=target)  # type: ignore[arg-type]


async def _compose_planned_result(
    *,
    state: dict[str, Any],
    candidate: ActiveTripCandidate,
    queried_at: datetime,
) -> VehicleEtaResult | None:
    if candidate.direction_id is None or candidate.terminal_stop_id is None:
        return None
    segments = _remaining_segments(
        candidate,
        shape_progress_m=float(state["shape_progress_m"]),
        origin_stop_sequence=state["current_origin_stop_sequence"],
        destination_stop_sequence=state["current_destination_stop_sequence"],
    )
    at_terminal = bool(
        candidate.planned_segments
        and float(state["shape_progress_m"])
        >= candidate.planned_segments[-1].destination_progress_m
    )
    if not segments and not at_terminal:
        return None

    if segments:
        catalog = _PlannedOnlyCatalog()

        async def resolver(segment, estimate_at, scope):  # type: ignore[no-untyped-def]
            return catalog.resolve(
                segment,
                estimate_at,
                scope,
                route_id=candidate.route_id,
                direction_id=candidate.direction_id,
            )

        projections = {
            (scenario, scope): await compose_eta_projection(
                segments=segments,
                queried_at=queried_at,
                scope=scope,
                scenario=scenario,
                resolver=resolver,
            )
            for scenario in ("current_time", "future_time")
            for scope in ("physical", "service")
        }
        next_stop_id = segments[0].destination_stop_id
    else:
        projections = {
            (scenario, scope): _arrived_projection(
                scope=scope,
                scenario=scenario,
                queried_at=queried_at,
            )
            for scenario in ("current_time", "future_time")
            for scope in ("physical", "service")
        }
        next_stop_id = candidate.terminal_stop_id

    return VehicleEtaResult(
        vehicle_prefix=state["vehicle_prefix"],
        trip_id=candidate.trip_id,
        route_id=candidate.route_id,
        direction_id=candidate.direction_id,
        next_stop_id=next_stop_id,
        terminal_stop_id=candidate.terminal_stop_id,
        planned_trip_end_at=planned_trip_end_at(
            arrival_seconds=candidate.terminal_arrival_seconds,
            queried_at=queried_at,
        ),
        remaining_segment_count=len(segments),
        current_time_physical=projections[("current_time", "physical")],
        current_time_service=projections[("current_time", "service")],
        future_time_physical=projections[("future_time", "physical")],
        future_time_service=projections[("future_time", "service")],
    )


async def refresh_missing_planned_eta_snapshots(
    session: AsyncSession,
    *,
    queried_at: datetime,
    active_trip_index: ActiveTripIndex,
) -> PlannedEtaSnapshotRefreshResult:
    result = await session.execute(
        text(
            """
            SELECT vehicle.vehicle_prefix, vehicle.source_timestamp,
                   vehicle.trip_id, vehicle.route_id, vehicle.shape_progress_m,
                   vehicle.current_origin_stop_sequence,
                   vehicle.current_destination_stop_sequence
            FROM realtime.vehicle_current_states AS vehicle
            LEFT JOIN realtime.vehicle_eta_snapshots AS snapshot
              ON snapshot.vehicle_prefix = vehicle.vehicle_prefix
            WHERE vehicle.map_match_status = 'resolved'
              AND vehicle.source_timestamp >= :fresh_after
              AND vehicle.projected_location IS NOT NULL
              AND vehicle.projected_at IS NOT NULL
              AND vehicle.projection_quality IN ('valid', 'reduced')
              AND vehicle.trip_id IS NOT NULL
              AND vehicle.route_id IS NOT NULL
              AND vehicle.shape_id IS NOT NULL
              AND vehicle.shape_position IS NOT NULL
              AND vehicle.shape_progress_m IS NOT NULL
              AND vehicle.distance_to_shape_m IS NOT NULL
              AND (
                    snapshot.vehicle_prefix IS NULL
                 OR snapshot.trip_id <> vehicle.trip_id
                 OR snapshot.generated_at < :snapshot_fresh_after
              )
            ORDER BY vehicle.vehicle_prefix
            """
        ),
        {
            "fresh_after": queried_at - timedelta(seconds=60),
            "snapshot_fresh_after": queried_at - _MAX_SNAPSHOT_AGE,
        },
    )
    states = [dict(row) for row in result.mappings()]
    rows: list[dict[str, Any]] = []
    unavailable = 0
    for state in states:
        candidate = active_trip_index.candidates_by_trip_id.get(state["trip_id"])
        if candidate is None:
            unavailable += 1
            continue
        eta = await _compose_planned_result(
            state=state,
            candidate=candidate,
            queried_at=queried_at,
        )
        if eta is None:
            unavailable += 1
            continue
        response = build_vehicle_eta_response(
            eta,
            queried_at=queried_at,
            calculation_mode="planned_baseline",
        )
        rows.append(
            {
                "vehicle_prefix": eta.vehicle_prefix,
                "source_timestamp": state["source_timestamp"],
                "generated_at": queried_at,
                "trip_id": eta.trip_id,
                "route_id": eta.route_id,
                "direction_id": eta.direction_id,
                "payload": response.model_dump(mode="json"),
            }
        )

    if rows:
        statement = insert(VehicleEtaSnapshot).values(rows)
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
    return PlannedEtaSnapshotRefreshResult(
        eligible_vehicle_count=len(states),
        snapshot_count=len(rows),
        unavailable_vehicle_count=unavailable,
    )
