from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.segment_estimate_catalog import load_segment_estimate_catalog
from app.services.vehicle_eta import (
    EtaProjection,
    EtaScenario,
    EtaScope,
    RemainingTripSegment,
    compose_eta_projection,
)


class VehicleNotFoundError(LookupError):
    pass


class VehicleEtaUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VehicleEtaResult:
    vehicle_prefix: str
    trip_id: str
    route_id: str
    direction_id: int
    next_stop_id: str
    terminal_stop_id: str
    remaining_segment_count: int
    current_time_physical: EtaProjection
    current_time_service: EtaProjection
    future_time_physical: EtaProjection
    future_time_service: EtaProjection


async def query_vehicle_eta(
    session: AsyncSession,
    *,
    vehicle_prefix: str,
    queried_at: datetime,
) -> VehicleEtaResult:
    if queried_at.tzinfo is None:
        raise ValueError("ETA timestamp must include a timezone.")

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
            LEFT JOIN core.gtfs_trips AS trip
              ON trip.feed_id = vehicle.feed_id
             AND trip.trip_id = vehicle.trip_id
            WHERE vehicle.vehicle_prefix = :vehicle_prefix
            """
        ),
        {"vehicle_prefix": vehicle_prefix},
    )
    state_rows = list(state_result.mappings())
    if not state_rows:
        raise VehicleNotFoundError(vehicle_prefix)
    state = state_rows[0]
    required = (
        "source_timestamp",
        "feed_id",
        "trip_id",
        "route_id",
        "direction_id",
        "shape_progress_m",
        "current_origin_stop_sequence",
        "current_destination_stop_sequence",
    )
    if any(state[field] is None for field in required):
        raise VehicleEtaUnavailableError(
            "Vehicle does not have a resolved trip and current segment."
        )
    if queried_at - state["source_timestamp"] > timedelta(minutes=5):
        raise VehicleEtaUnavailableError("Vehicle position is older than five minutes.")

    stops_result = await session.execute(
        text(
            """
            SELECT stop_id, stop_sequence, shape_progress_m,
                   arrival_seconds, departure_seconds
            FROM core.gtfs_stop_times
            WHERE feed_id = :feed_id
              AND trip_id = :trip_id
              AND stop_sequence >= :origin_stop_sequence
            ORDER BY stop_sequence
            """
        ),
        {
            "feed_id": state["feed_id"],
            "trip_id": state["trip_id"],
            "origin_stop_sequence": state["current_origin_stop_sequence"],
        },
    )
    stops = list(stops_result.mappings())
    if len(stops) < 2:
        raise VehicleEtaUnavailableError("Trip does not have a remaining stop pair.")
    if (
        stops[0]["stop_sequence"] != state["current_origin_stop_sequence"]
        or stops[1]["stop_sequence"] != state["current_destination_stop_sequence"]
    ):
        raise VehicleEtaUnavailableError("Current segment does not match the GTFS trip.")

    origin_progress = stops[0]["shape_progress_m"]
    destination_progress = stops[1]["shape_progress_m"]
    if (
        origin_progress is None
        or destination_progress is None
        or destination_progress <= origin_progress
    ):
        raise VehicleEtaUnavailableError("Current segment does not have usable shape progress.")
    remaining_fraction = max(
        0.0,
        min(
            1.0,
            (destination_progress - state["shape_progress_m"])
            / (destination_progress - origin_progress),
        ),
    )

    segments: list[RemainingTripSegment] = []
    for index, (origin, destination) in enumerate(zip(stops, stops[1:], strict=False)):
        if origin["stop_id"] == destination["stop_id"]:
            if destination["arrival_seconds"] > origin["departure_seconds"]:
                raise VehicleEtaUnavailableError(
                    "Trip contains a timed segment whose stops have the same identifier."
                )
            continue
        segments.append(
            RemainingTripSegment(
                origin_stop_id=origin["stop_id"],
                destination_stop_id=destination["stop_id"],
                origin_stop_sequence=origin["stop_sequence"],
                destination_stop_sequence=destination["stop_sequence"],
                remaining_fraction=remaining_fraction if index == 0 else 1.0,
            )
        )
    if not segments:
        raise VehicleEtaUnavailableError("Trip does not have a measurable remaining segment.")

    catalog = await load_segment_estimate_catalog(
        session,
        segments=tuple(segments),
        route_id=state["route_id"],
        direction_id=state["direction_id"],
        queried_at=queried_at,
    )

    async def resolve_segment(
        segment: RemainingTripSegment,
        estimate_at: datetime,
        scope: EtaScope,
    ):  # type: ignore[no-untyped-def]
        return catalog.resolve(segment, estimate_at, scope)

    projections: dict[tuple[EtaScenario, EtaScope], EtaProjection] = {}
    for scenario in ("current_time", "future_time"):
        for scope in ("physical", "service"):
            projections[(scenario, scope)] = await compose_eta_projection(
                segments=tuple(segments),
                queried_at=queried_at,
                scope=scope,
                scenario=scenario,
                resolver=resolve_segment,
            )

    return VehicleEtaResult(
        vehicle_prefix=state["vehicle_prefix"],
        trip_id=state["trip_id"],
        route_id=state["route_id"],
        direction_id=state["direction_id"],
        next_stop_id=segments[0].destination_stop_id,
        terminal_stop_id=stops[-1]["stop_id"],
        remaining_segment_count=len(segments),
        current_time_physical=projections[("current_time", "physical")],
        current_time_service=projections[("current_time", "service")],
        future_time_physical=projections[("future_time", "physical")],
        future_time_service=projections[("future_time", "service")],
    )
