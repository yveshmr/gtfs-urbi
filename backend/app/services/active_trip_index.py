from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GtfsFeed, GtfsRoute, GtfsService, GtfsServiceException, GtfsTrip
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
class ActiveTripCandidate:
    feed_id: object
    trip_id: str
    route_id: str
    shape_id: str | None


@dataclass(frozen=True, slots=True)
class ActiveTripIndex:
    candidates_by_key: dict[TripCorrelationKey, tuple[str, ...]]
    candidates_by_trip_id: dict[str, ActiveTripCandidate]


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

    candidates_by_key: dict[TripCorrelationKey, list[str]] = defaultdict(list)
    candidates_by_trip_id: dict[str, ActiveTripCandidate] = {}
    for row in result:
        line = normalize_model4_line(row.short_name)
        if line is None or row.direction_id is None or row.start_seconds is None:
            continue
        key = TripCorrelationKey(
            line=line,
            direction=str(row.direction_id),
            planned_time=_service_time(row.start_seconds),
        )
        candidates_by_key[key].append(row.trip_id)
        candidates_by_trip_id[row.trip_id] = ActiveTripCandidate(
            feed_id=row.feed_id,
            trip_id=row.trip_id,
            route_id=row.route_id,
            shape_id=row.shape_id,
        )

    return ActiveTripIndex(
        candidates_by_key={key: tuple(value) for key, value in candidates_by_key.items()},
        candidates_by_trip_id=candidates_by_trip_id,
    )
