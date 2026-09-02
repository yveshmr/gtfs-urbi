from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GtfsFeed,
    GtfsRoute,
    GtfsService,
    GtfsServiceException,
    GtfsShapeSegment,
    GtfsStopTime,
    GtfsTrip,
)
from app.services.trip_correlation import TripCorrelationKey, normalize_model4_line

_WEEKDAY_COLUMNS = (
    GtfsService.monday,
    GtfsService.tuesday,
    GtfsService.wednesday,
    GtfsService.thursday,
    GtfsService.friday,
    GtfsService.saturday,
    GtfsService.sunday,
)


@dataclass(frozen=True, slots=True)
class PlannedTripSegment:
    origin_stop_id: str
    destination_stop_id: str
    origin_stop_sequence: int
    destination_stop_sequence: int
    origin_progress_m: float
    destination_progress_m: float
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class ActiveTripCandidate:
    feed_id: object
    trip_id: str
    route_id: str
    shape_id: str | None
    direction_id: int | None = None
    planned_segments: tuple[PlannedTripSegment, ...] = ()
    terminal_stop_id: str | None = None
    terminal_arrival_seconds: int | None = None
    shape_total_distance_m: float | None = None


@dataclass(frozen=True, slots=True)
class ActiveTripIndex:
    candidates_by_key: dict[TripCorrelationKey, tuple[str, ...]]
    candidates_by_trip_id: dict[str, ActiveTripCandidate]
    service_date: date | None = None


def _service_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


async def load_active_trip_index(
    session: AsyncSession,
    *,
    service_date: date,
) -> ActiveTripIndex:
    latest_feed = (
        select(GtfsFeed.id).order_by(GtfsFeed.retrieved_at.desc()).limit(1).scalar_subquery()
    )
    exception_condition = and_(
        GtfsServiceException.feed_id == GtfsService.feed_id,
        GtfsServiceException.service_id == GtfsService.service_id,
        GtfsServiceException.service_date == service_date,
    )
    regular_service = and_(
        GtfsService.start_date <= service_date,
        GtfsService.end_date >= service_date,
        _WEEKDAY_COLUMNS[service_date.weekday()].is_(True),
    )
    active_service = or_(
        GtfsServiceException.exception_type == 1,
        and_(GtfsServiceException.exception_type.is_(None), regular_service),
    )
    statement = (
        select(
            GtfsTrip.feed_id,
            GtfsTrip.trip_id,
            GtfsTrip.route_id,
            GtfsTrip.shape_id,
            GtfsTrip.direction_id,
            GtfsTrip.start_seconds,
            GtfsRoute.short_name,
            (
                select(func.max(GtfsShapeSegment.end_distance_m))
                .where(
                    GtfsShapeSegment.feed_id == GtfsTrip.feed_id,
                    GtfsShapeSegment.shape_id == GtfsTrip.shape_id,
                )
                .correlate(GtfsTrip)
                .scalar_subquery()
            ).label("shape_total_distance_m"),
        )
        .join(
            GtfsRoute,
            and_(
                GtfsRoute.feed_id == GtfsTrip.feed_id,
                GtfsRoute.route_id == GtfsTrip.route_id,
            ),
        )
        .join(
            GtfsService,
            and_(
                GtfsService.feed_id == GtfsTrip.feed_id,
                GtfsService.service_id == GtfsTrip.service_id,
            ),
        )
        .outerjoin(GtfsServiceException, exception_condition)
        .where(GtfsTrip.feed_id == latest_feed, active_service)
    )
    result = await session.execute(statement)
    trip_rows = list(result)

    trip_ids = [row.trip_id for row in trip_rows]
    stops_by_trip_id: dict[str, list[object]] = defaultdict(list)
    if trip_ids:
        stop_result = await session.execute(
            select(
                GtfsStopTime.trip_id,
                GtfsStopTime.stop_id,
                GtfsStopTime.stop_sequence,
                GtfsStopTime.arrival_seconds,
                GtfsStopTime.departure_seconds,
                GtfsStopTime.shape_progress_m,
                GtfsStopTime.shape_projection_quality,
            )
            .where(
                GtfsStopTime.feed_id == latest_feed,
                GtfsStopTime.trip_id.in_(trip_ids),
            )
            .order_by(GtfsStopTime.trip_id, GtfsStopTime.stop_sequence)
        )
        for stop in stop_result:
            stops_by_trip_id[stop.trip_id].append(stop)

    candidates_by_key: dict[TripCorrelationKey, list[str]] = defaultdict(list)
    candidates_by_trip_id: dict[str, ActiveTripCandidate] = {}
    for row in trip_rows:
        line = normalize_model4_line(row.short_name)
        if line is None or row.direction_id is None or row.start_seconds is None:
            continue
        key = TripCorrelationKey(
            line=line,
            direction=str(row.direction_id),
            planned_time=_service_time(row.start_seconds),
        )
        candidates_by_key[key].append(row.trip_id)
        stops = stops_by_trip_id.get(row.trip_id, [])
        planned_segments: list[PlannedTripSegment] = []
        for origin, destination in zip(stops, stops[1:], strict=False):
            origin_progress = origin.shape_progress_m
            destination_progress = destination.shape_progress_m
            terminal_wrap = bool(
                destination is stops[-1]
                and row.shape_total_distance_m is not None
                and origin_progress is not None
                and destination_progress is not None
                and destination_progress <= origin_progress
                and row.shape_total_distance_m > origin_progress
            )
            if terminal_wrap:
                destination_progress = row.shape_total_distance_m
            if (
                (origin.stop_id == destination.stop_id and not terminal_wrap)
                or origin_progress is None
                or destination_progress is None
                or destination_progress <= origin_progress
                or destination.arrival_seconds <= origin.departure_seconds
                or origin.shape_projection_quality not in {"valid", "reduced"}
                or destination.shape_projection_quality not in {"valid", "reduced"}
            ):
                continue
            planned_segments.append(
                PlannedTripSegment(
                    origin_stop_id=origin.stop_id,
                    destination_stop_id=destination.stop_id,
                    origin_stop_sequence=origin.stop_sequence,
                    destination_stop_sequence=destination.stop_sequence,
                    origin_progress_m=float(origin_progress),
                    destination_progress_m=float(destination_progress),
                    duration_seconds=float(
                        destination.arrival_seconds - origin.departure_seconds
                    ),
                )
            )
        candidates_by_trip_id[row.trip_id] = ActiveTripCandidate(
            feed_id=row.feed_id,
            trip_id=row.trip_id,
            route_id=row.route_id,
            shape_id=row.shape_id,
            direction_id=row.direction_id,
            planned_segments=tuple(planned_segments),
            terminal_stop_id=stops[-1].stop_id if stops else None,
            terminal_arrival_seconds=(stops[-1].arrival_seconds if stops else None),
            shape_total_distance_m=(
                float(row.shape_total_distance_m)
                if row.shape_total_distance_m is not None
                else None
            ),
        )

    return ActiveTripIndex(
        candidates_by_key={key: tuple(value) for key, value in candidates_by_key.items()},
        candidates_by_trip_id=candidates_by_trip_id,
        service_date=service_date,
    )
