from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
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
from app.services.vehicle_eta import EtaScope, RemainingTripSegment

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True, slots=True)
class PlannedTraversal:
    departure_at: datetime
    duration_seconds: float


@dataclass(slots=True)
class SegmentEstimateCatalog:
    route_id: str
    direction_id: int
    live_by_key: dict[str, LiveEstimateCandidate]
    profiles_by_key_and_slot: dict[tuple[str, str, int], EstimateCandidate]
    planned_by_scope_and_pair: dict[
        tuple[str, str, str], tuple[PlannedTraversal, ...]
    ]

    def resolve(
        self,
        segment: RemainingTripSegment,
        estimate_at: datetime,
        scope: EtaScope,
    ) -> ResolvedSegmentEstimate:
        physical, service = metric_identities_for_segment(
            origin_stop_id=segment.origin_stop_id,
            destination_stop_id=segment.destination_stop_id,
            route_id=self.route_id,
            direction_id=self.direction_id,
        )
        identity = physical if scope == "physical" else service
        live = self.live_by_key.get(identity.metric_key)
        historical = tuple(
            HistoricalEstimateCandidate(
                value_seconds=candidate.value_seconds,
                reliability=candidate.reliability,
                sample_count=candidate.sample_count,
                slot_offset_minutes=offset,
            )
            for day_type, slot_index, offset in historical_profile_slots(estimate_at)
            if (
                candidate := self.profiles_by_key_and_slot.get(
                    (identity.metric_key, day_type, slot_index)
                )
            )
            is not None
        )
        planned = self._planned_candidate(segment, estimate_at, scope)
        return resolve_segment_estimate(
            now=estimate_at,
            live=live,
            historical=historical,
            gtfs_planned=planned,
        )

    def _planned_candidate(
        self,
        segment: RemainingTripSegment,
        estimate_at: datetime,
        scope: EtaScope,
    ) -> EstimateCandidate | None:
        traversals = self.planned_by_scope_and_pair.get(
            (scope, segment.origin_stop_id, segment.destination_stop_id),
            (),
        )
        for offset in FALLBACK_SLOT_OFFSETS_MINUTES:
            local = (estimate_at + timedelta(minutes=offset)).astimezone(
                _OPERATIONAL_TIMEZONE
            )
            window_start = local.replace(
                minute=local.minute - local.minute % 5,
                second=0,
                microsecond=0,
            )
            window_end = window_start + timedelta(minutes=5)
            durations = [
                item.duration_seconds
                for item in traversals
                if window_start <= item.departure_at < window_end
            ]
            if durations:
                return EstimateCandidate(
                    value_seconds=statistics.fmean(durations),
                    reliability=1.0,
                    sample_count=len(durations),
                )
        return None


async def load_segment_estimate_catalog(
    session: AsyncSession,
    *,
    segments: tuple[RemainingTripSegment, ...],
    route_id: str,
    direction_id: int,
    queried_at: datetime,
) -> SegmentEstimateCatalog:
    unique_pairs = tuple(
        dict.fromkeys(
            (segment.origin_stop_id, segment.destination_stop_id)
            for segment in segments
        )
    )
    identities: list[SegmentMetricIdentity] = []
    for origin_stop_id, destination_stop_id in unique_pairs:
        for identity in metric_identities_for_segment(
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
        ):
            identities.append(identity)
    metric_keys = [identity.metric_key for identity in identities]

    live_result = await session.execute(
        text(
            """
            SELECT metric_key, mean_seconds, reliability,
                   sample_count_accepted, window_start, window_end
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

    service_date = operational_service_date(queried_at)
    reference_start = historical_retention_start(service_date)
    reference_end = service_date - timedelta(days=1)
    profile_result = await session.execute(
        text(
            """
            SELECT metric_key, day_type, slot_index, mean_seconds,
                   reliability, sample_count_accepted
            FROM analytics.segment_profiles_5m
            WHERE metric_key = ANY(CAST(:metric_keys AS text[]))
              AND reference_start_date = :reference_start
              AND reference_end_date = :reference_end
              AND mean_seconds IS NOT NULL
              AND sample_count_accepted > 0
            """
        ),
        {
            "metric_keys": metric_keys,
            "reference_start": reference_start,
            "reference_end": reference_end,
        },
    )
    profiles_by_key_and_slot: dict[tuple[str, str, int], EstimateCandidate] = {}
    for row in profile_result.mappings():
        profiles_by_key_and_slot[
            (row["metric_key"], row["day_type"], row["slot_index"])
        ] = EstimateCandidate(
            value_seconds=row["mean_seconds"],
            reliability=row["reliability"],
            sample_count=row["sample_count_accepted"],
        )

    local_date = queried_at.astimezone(_OPERATIONAL_TIMEZONE).date()
    requested_dates = [
        {"service_date": (local_date + timedelta(days=offset)).isoformat()}
        for offset in (-1, 0, 1, 2)
    ]
    requested_pairs = [
        {"origin_stop_id": origin, "destination_stop_id": destination}
        for origin, destination in unique_pairs
    ]
    planned_result = await session.execute(
        text(
            """
            WITH requested_pairs AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:pairs AS jsonb)) AS pair(
                    origin_stop_id text,
                    destination_stop_id text
                )
            ),
            requested_dates AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:dates AS jsonb)) AS requested(
                    service_date date
                )
            ),
            latest_feed AS (
                SELECT id
                FROM core.gtfs_feeds
                ORDER BY retrieved_at DESC
                LIMIT 1
            ),
            scheduled AS (
                SELECT
                    pair.origin_stop_id,
                    pair.destination_stop_id,
                    trip.route_id,
                    trip.direction_id,
                    requested.service_date,
                    origin.departure_seconds,
                    destination.arrival_seconds - origin.departure_seconds
                        AS duration_seconds,
                    service.monday, service.tuesday, service.wednesday,
                    service.thursday, service.friday, service.saturday,
                    service.sunday, service.start_date, service.end_date,
                    exception.exception_type
                FROM requested_pairs AS pair
                CROSS JOIN requested_dates AS requested
                CROSS JOIN latest_feed AS feed
                JOIN core.gtfs_stop_times AS origin
                  ON origin.feed_id = feed.id
                 AND origin.stop_id = pair.origin_stop_id
                JOIN LATERAL (
                    SELECT candidate.stop_id, candidate.arrival_seconds
                    FROM core.gtfs_stop_times AS candidate
                    WHERE candidate.feed_id = origin.feed_id
                      AND candidate.trip_id = origin.trip_id
                      AND candidate.stop_sequence > origin.stop_sequence
                    ORDER BY candidate.stop_sequence
                    LIMIT 1
                ) AS destination
                  ON destination.stop_id = pair.destination_stop_id
                 AND destination.arrival_seconds > origin.departure_seconds
                JOIN core.gtfs_trips AS trip
                  ON trip.feed_id = origin.feed_id
                 AND trip.trip_id = origin.trip_id
                JOIN core.gtfs_services AS service
                  ON service.feed_id = trip.feed_id
                 AND service.service_id = trip.service_id
                LEFT JOIN core.gtfs_service_exceptions AS exception
                  ON exception.feed_id = service.feed_id
                 AND exception.service_id = service.service_id
                 AND exception.service_date = requested.service_date
            )
            SELECT origin_stop_id, destination_stop_id, route_id, direction_id,
                   service_date, departure_seconds, duration_seconds
            FROM scheduled
            WHERE
                exception_type = 1
                OR (
                    exception_type IS NULL
                    AND start_date <= service_date
                    AND end_date >= service_date
                    AND CASE EXTRACT(ISODOW FROM service_date)::integer
                        WHEN 1 THEN monday
                        WHEN 2 THEN tuesday
                        WHEN 3 THEN wednesday
                        WHEN 4 THEN thursday
                        WHEN 5 THEN friday
                        WHEN 6 THEN saturday
                        WHEN 7 THEN sunday
                    END
                )
            """
        ),
        {"pairs": json.dumps(requested_pairs), "dates": json.dumps(requested_dates)},
    )
    planned: dict[tuple[str, str, str], list[PlannedTraversal]] = defaultdict(list)
    for row in planned_result.mappings():
        departure_at = datetime.combine(
            row["service_date"],
            time.min,
            tzinfo=_OPERATIONAL_TIMEZONE,
        ) + timedelta(seconds=row["departure_seconds"])
        traversal = PlannedTraversal(
            departure_at=departure_at,
            duration_seconds=row["duration_seconds"],
        )
        physical_key = (
            "physical",
            row["origin_stop_id"],
            row["destination_stop_id"],
        )
        planned[physical_key].append(traversal)
        if row["route_id"] == route_id and row["direction_id"] == direction_id:
            service_key = (
                "service",
                row["origin_stop_id"],
                row["destination_stop_id"],
            )
            planned[service_key].append(traversal)

    return SegmentEstimateCatalog(
        route_id=route_id,
        direction_id=direction_id,
        live_by_key=live_by_key,
        profiles_by_key_and_slot=profiles_by_key_and_slot,
        planned_by_scope_and_pair={
            key: tuple(value) for key, value in planned.items()
        },
    )
