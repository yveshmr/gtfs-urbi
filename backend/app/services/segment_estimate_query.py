from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.segment_aggregation import (
    FALLBACK_SLOT_OFFSETS_MINUTES,
    EstimateCandidate,
    HistoricalEstimateCandidate,
    LiveEstimateCandidate,
    ResolvedSegmentEstimate,
    SegmentMetricIdentity,
    historical_profile_slots,
    historical_retention_start,
    metric_identities_for_segment,
    operational_service_date,
    resolve_segment_estimate,
)

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True, slots=True)
class SegmentEstimatePair:
    physical: ResolvedSegmentEstimate
    service: ResolvedSegmentEstimate | None


async def _query_gtfs_planned_candidates(
    session: AsyncSession,
    *,
    origin_stop_id: str,
    destination_stop_id: str,
    queried_at: datetime,
    include_physical: bool,
    route_id: str | None,
    direction_id: int | None,
) -> dict[str, EstimateCandidate]:
    windows: list[dict[str, object]] = []
    for offset in FALLBACK_SLOT_OFFSETS_MINUTES:
        local = (queried_at + timedelta(minutes=offset)).astimezone(_OPERATIONAL_TIMEZONE)
        slot_start_seconds = (local.hour * 60 + local.minute // 5 * 5) * 60
        windows.extend(
            (
                {
                    "service_date": local.date().isoformat(),
                    "slot_start_seconds": slot_start_seconds,
                    "offset_minutes": offset,
                },
                {
                    "service_date": (local.date() - timedelta(days=1)).isoformat(),
                    "slot_start_seconds": slot_start_seconds + 86400,
                    "offset_minutes": offset,
                },
            )
        )

    result = await session.execute(
        text(
            """
            WITH requested_windows AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:windows AS jsonb)) AS requested(
                    service_date date,
                    slot_start_seconds integer,
                    offset_minutes integer
                )
            ),
            latest_feed AS (
                SELECT id
                FROM core.gtfs_feeds
                ORDER BY retrieved_at DESC
                LIMIT 1
            ),
            active_trips AS (
                SELECT
                    trip.feed_id,
                    trip.trip_id,
                    trip.route_id,
                    trip.direction_id,
                    requested.slot_start_seconds,
                    requested.offset_minutes
                FROM requested_windows AS requested
                CROSS JOIN latest_feed AS feed
                JOIN core.gtfs_trips AS trip ON trip.feed_id = feed.id
                JOIN core.gtfs_services AS service
                  ON service.feed_id = trip.feed_id
                 AND service.service_id = trip.service_id
                LEFT JOIN core.gtfs_service_exceptions AS exception
                  ON exception.feed_id = service.feed_id
                 AND exception.service_id = service.service_id
                 AND exception.service_date = requested.service_date
                WHERE
                    exception.exception_type = 1
                    OR (
                        exception.exception_type IS NULL
                        AND service.start_date <= requested.service_date
                        AND service.end_date >= requested.service_date
                        AND CASE EXTRACT(ISODOW FROM requested.service_date)::integer
                            WHEN 1 THEN service.monday
                            WHEN 2 THEN service.tuesday
                            WHEN 3 THEN service.wednesday
                            WHEN 4 THEN service.thursday
                            WHEN 5 THEN service.friday
                            WHEN 6 THEN service.saturday
                            WHEN 7 THEN service.sunday
                        END
                    )
            )
            SELECT
                trip.route_id,
                trip.direction_id,
                trip.offset_minutes,
                destination.arrival_seconds - origin.departure_seconds
                    AS duration_seconds
            FROM active_trips AS trip
            JOIN core.gtfs_stop_times AS origin
              ON origin.feed_id = trip.feed_id
             AND origin.trip_id = trip.trip_id
             AND origin.stop_id = :origin_stop_id
             AND origin.departure_seconds >= trip.slot_start_seconds
             AND origin.departure_seconds < trip.slot_start_seconds + 300
            JOIN LATERAL (
                SELECT candidate.stop_id, candidate.arrival_seconds
                FROM core.gtfs_stop_times AS candidate
                WHERE candidate.feed_id = origin.feed_id
                  AND candidate.trip_id = origin.trip_id
                  AND candidate.stop_sequence > origin.stop_sequence
                ORDER BY candidate.stop_sequence
                LIMIT 1
            ) AS destination ON destination.stop_id = :destination_stop_id
            WHERE destination.arrival_seconds > origin.departure_seconds
            """
        ),
        {
            "windows": json.dumps(windows),
            "origin_stop_id": origin_stop_id,
            "destination_stop_id": destination_stop_id,
        },
    )
    rows = list(result.mappings())
    candidates: dict[str, EstimateCandidate] = {}

    def first_available(
        eligible_rows: list[object],
    ) -> EstimateCandidate | None:
        for offset in FALLBACK_SLOT_OFFSETS_MINUTES:
            durations = [
                row["duration_seconds"] for row in eligible_rows if row["offset_minutes"] == offset
            ]
            if durations:
                return EstimateCandidate(
                    value_seconds=statistics.fmean(durations),
                    reliability=1.0,
                    sample_count=len(durations),
                )
        return None

    if include_physical:
        physical = first_available(rows)
        if physical is not None:
            candidates["physical"] = physical
    if route_id is not None and direction_id is not None:
        service = first_available(
            [
                row
                for row in rows
                if row["route_id"] == route_id and row["direction_id"] == direction_id
            ]
        )
        if service is not None:
            candidates["service"] = service
    return candidates


async def query_segment_estimates(
    session: AsyncSession,
    *,
    origin_stop_id: str,
    destination_stop_id: str,
    queried_at: datetime,
    route_id: str | None = None,
    direction_id: int | None = None,
) -> SegmentEstimatePair:
    if queried_at.tzinfo is None:
        raise ValueError("The estimate timestamp must include a timezone.")
    if (route_id is None) != (direction_id is None):
        raise ValueError("Route and direction must be provided together.")

    identities: tuple[SegmentMetricIdentity, ...]
    if route_id is None or direction_id is None:
        identities = (
            SegmentMetricIdentity(
                scope="physical",
                origin_stop_id=origin_stop_id,
                destination_stop_id=destination_stop_id,
            ),
        )
    else:
        identities = metric_identities_for_segment(
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
        )

    metric_keys = [identity.metric_key for identity in identities]
    live_result = await session.execute(
        text(
            """
            SELECT metric_key, mean_seconds, reliability,
                   sample_count_accepted, window_end
            FROM analytics.segment_live_metrics_5m
            WHERE metric_key = ANY(CAST(:metric_keys AS text[]))
              AND mean_seconds IS NOT NULL
              AND sample_count_accepted > 0
              AND window_start <= :queried_at
            """
        ),
        {"metric_keys": metric_keys, "queried_at": queried_at},
    )
    live_by_key = {
        row["metric_key"]: LiveEstimateCandidate(
            value_seconds=row["mean_seconds"],
            reliability=row["reliability"],
            sample_count=row["sample_count_accepted"],
            window_end=row["window_end"],
        )
        for row in live_result.mappings()
    }

    requested_slots = historical_profile_slots(queried_at)
    local_service_date = operational_service_date(queried_at)
    reference_start = historical_retention_start(local_service_date)
    reference_end = local_service_date - timedelta(days=1)
    historical_result = await session.execute(
        text(
            """
            SELECT metric_key, day_type, slot_index, mean_seconds,
                   reliability, sample_count_accepted
            FROM analytics.segment_profiles_5m
            WHERE metric_key = ANY(CAST(:metric_keys AS text[]))
              AND day_type = ANY(CAST(:day_types AS text[]))
              AND slot_index = ANY(CAST(:slot_indexes AS smallint[]))
              AND reference_start_date = :reference_start
              AND reference_end_date = :reference_end
              AND mean_seconds IS NOT NULL
              AND sample_count_accepted > 0
            """
        ),
        {
            "metric_keys": metric_keys,
            "day_types": list({day_type for day_type, _, _ in requested_slots}),
            "slot_indexes": list({slot for _, slot, _ in requested_slots}),
            "reference_start": reference_start,
            "reference_end": reference_end,
        },
    )
    profile_by_key_and_slot = {
        (row["metric_key"], row["day_type"], row["slot_index"]): row
        for row in historical_result.mappings()
    }

    historical_by_scope: dict[str, tuple[HistoricalEstimateCandidate, ...]] = {}
    preliminary_by_scope: dict[str, ResolvedSegmentEstimate] = {}
    for identity in identities:
        historical_candidates: list[HistoricalEstimateCandidate] = []
        for day_type, slot_index, offset in requested_slots:
            row = profile_by_key_and_slot.get((identity.metric_key, day_type, slot_index))
            if row is not None:
                historical_candidates.append(
                    HistoricalEstimateCandidate(
                        value_seconds=row["mean_seconds"],
                        reliability=row["reliability"],
                        sample_count=row["sample_count_accepted"],
                        slot_offset_minutes=offset,
                    )
                )

        historical_by_scope[identity.scope] = tuple(historical_candidates)
        preliminary_by_scope[identity.scope] = resolve_segment_estimate(
            now=queried_at,
            live=live_by_key.get(identity.metric_key),
            historical=tuple(historical_candidates),
            gtfs_planned=None,
        )

    missing_scopes = {
        scope
        for scope, estimate in preliminary_by_scope.items()
        if estimate.source == "unavailable"
    }
    planned_by_scope: dict[str, EstimateCandidate] = {}
    if missing_scopes:
        planned_by_scope = await _query_gtfs_planned_candidates(
            session,
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            queried_at=queried_at,
            include_physical="physical" in missing_scopes,
            route_id=route_id if "service" in missing_scopes else None,
            direction_id=direction_id if "service" in missing_scopes else None,
        )

    resolved_by_scope: dict[str, ResolvedSegmentEstimate] = {}
    for identity in identities:
        preliminary = preliminary_by_scope[identity.scope]
        resolved_by_scope[identity.scope] = (
            preliminary
            if preliminary.source != "unavailable"
            else resolve_segment_estimate(
                now=queried_at,
                live=None,
                historical=historical_by_scope[identity.scope],
                gtfs_planned=planned_by_scope.get(identity.scope),
            )
        )

    return SegmentEstimatePair(
        physical=resolved_by_scope["physical"],
        service=resolved_by_scope.get("service"),
    )
