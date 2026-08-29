from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
class SegmentEstimateRequest:
    origin_stop_id: str
    destination_stop_id: str
    route_id: str
    direction_id: int


@dataclass(slots=True)
class SegmentEstimateCatalog:
    live_by_key: dict[str, LiveEstimateCandidate]
    profiles_by_key_and_slot: dict[tuple[str, str, int], EstimateCandidate]
    planned_by_scope_pair_and_slot: dict[
        tuple[str, str, str, str | None, int | None, date, int], EstimateCandidate
    ]

    def resolve(
        self,
        segment: RemainingTripSegment,
        estimate_at: datetime,
        scope: EtaScope,
        *,
        route_id: str,
        direction_id: int,
    ) -> ResolvedSegmentEstimate:
        physical, service = metric_identities_for_segment(
            origin_stop_id=segment.origin_stop_id,
            destination_stop_id=segment.destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
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
        planned = self._planned_candidate(
            segment,
            estimate_at,
            scope,
            route_id=route_id,
            direction_id=direction_id,
        )
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
        *,
        route_id: str,
        direction_id: int,
    ) -> EstimateCandidate | None:
        for offset in FALLBACK_SLOT_OFFSETS_MINUTES:
            local = (estimate_at + timedelta(minutes=offset)).astimezone(
                _OPERATIONAL_TIMEZONE
            )
            window_start = local.replace(
                minute=local.minute - local.minute % 5,
                second=0,
                microsecond=0,
            )
            slot_index = (window_start.hour * 60 + window_start.minute) // 5
            candidate = self.planned_by_scope_pair_and_slot.get(
                (
                    scope,
                    segment.origin_stop_id,
                    segment.destination_stop_id,
                    route_id if scope == "service" else None,
                    direction_id if scope == "service" else None,
                    window_start.date(),
                    slot_index,
                )
            )
            if candidate is not None:
                return candidate
        return None


async def load_segment_estimate_catalog(
    session: AsyncSession,
    *,
    segments: tuple[RemainingTripSegment, ...],
    route_id: str,
    direction_id: int,
    queried_at: datetime,
) -> SegmentEstimateCatalog:
    requests = tuple(
        SegmentEstimateRequest(
            origin_stop_id=segment.origin_stop_id,
            destination_stop_id=segment.destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
        )
        for segment in segments
    )
    return await load_fleet_segment_estimate_catalog(
        session,
        requests=requests,
        queried_at=queried_at,
    )


async def load_fleet_segment_estimate_catalog(
    session: AsyncSession,
    *,
    requests: tuple[SegmentEstimateRequest, ...],
    queried_at: datetime,
) -> SegmentEstimateCatalog:
    unique_requests = tuple(dict.fromkeys(requests))
    unique_pairs = tuple(
        dict.fromkeys(
            (request.origin_stop_id, request.destination_stop_id)
            for request in unique_requests
        )
    )
    identities: list[SegmentMetricIdentity] = []
    physical_pairs: set[tuple[str, str]] = set()
    for request in unique_requests:
        pair = (request.origin_stop_id, request.destination_stop_id)
        if pair not in physical_pairs:
            physical_pairs.add(pair)
            identities.append(
                metric_identities_for_segment(
                    origin_stop_id=request.origin_stop_id,
                    destination_stop_id=request.destination_stop_id,
                    route_id=request.route_id,
                    direction_id=request.direction_id,
                )[0]
            )
        for identity in metric_identities_for_segment(
            origin_stop_id=request.origin_stop_id,
            destination_stop_id=request.destination_stop_id,
            route_id=request.route_id,
            direction_id=request.direction_id,
        )[1:]:
            identities.append(identity)
    metric_keys = list(dict.fromkeys(identity.metric_key for identity in identities))

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
            requested_services AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:services AS jsonb)) AS requested(
                    origin_stop_id text,
                    destination_stop_id text,
                    route_id text,
                    direction_id integer
                )
            ),
            latest_feed AS (
                SELECT id
                FROM core.gtfs_feeds
                ORDER BY retrieved_at DESC
                LIMIT 1
            ),
            traversals AS (
                SELECT
                    pair.origin_stop_id,
                    pair.destination_stop_id,
                    trip.route_id,
                    trip.direction_id,
                    origin.departure_seconds,
                    destination.arrival_seconds - origin.departure_seconds
                        AS duration_seconds,
                    service.monday, service.tuesday, service.wednesday,
                    service.thursday, service.friday, service.saturday,
                    service.sunday, service.start_date, service.end_date,
                    service.feed_id AS service_feed_id,
                    service.service_id
                FROM requested_pairs AS pair
                CROSS JOIN latest_feed AS feed
                JOIN core.gtfs_stop_times AS origin
                  ON origin.feed_id = feed.id
                 AND origin.stop_id = pair.origin_stop_id
                JOIN core.gtfs_stop_times AS destination
                  ON destination.feed_id = origin.feed_id
                 AND destination.trip_id = origin.trip_id
                 AND destination.stop_sequence = origin.stop_sequence + 1
                 AND destination.stop_id = pair.destination_stop_id
                 AND destination.arrival_seconds > origin.departure_seconds
                JOIN core.gtfs_trips AS trip
                  ON trip.feed_id = origin.feed_id
                 AND trip.trip_id = origin.trip_id
                JOIN core.gtfs_services AS service
                  ON service.feed_id = trip.feed_id
                 AND service.service_id = trip.service_id
            ),
            scheduled AS (
                SELECT traversal.*, requested.service_date,
                       exception.exception_type
                FROM traversals AS traversal
                CROSS JOIN requested_dates AS requested
                LEFT JOIN core.gtfs_service_exceptions AS exception
                  ON exception.feed_id = traversal.service_feed_id
                 AND exception.service_id = traversal.service_id
                 AND exception.service_date = requested.service_date
            ),
            active AS MATERIALIZED (
                SELECT origin_stop_id, destination_stop_id, route_id, direction_id,
                       service_date + (departure_seconds / 86400)::integer
                           AS departure_date,
                       ((departure_seconds % 86400) / 300)::integer AS slot_index,
                       duration_seconds
                FROM scheduled
                WHERE exception_type = 1
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
            ),
            physical AS (
                SELECT 'physical'::text AS scope,
                       origin_stop_id, destination_stop_id,
                       NULL::text AS route_id, NULL::integer AS direction_id,
                       departure_date, slot_index,
                       AVG(duration_seconds) AS mean_duration_seconds,
                       COUNT(*)::integer AS trip_count
                FROM active
                GROUP BY origin_stop_id, destination_stop_id,
                         departure_date, slot_index
            ),
            service AS (
                SELECT 'service'::text AS scope,
                       active.origin_stop_id, active.destination_stop_id,
                       active.route_id, active.direction_id,
                       active.departure_date, active.slot_index,
                       AVG(active.duration_seconds) AS mean_duration_seconds,
                       COUNT(*)::integer AS trip_count
                FROM active
                JOIN requested_services AS requested
                  ON requested.origin_stop_id = active.origin_stop_id
                 AND requested.destination_stop_id = active.destination_stop_id
                 AND requested.route_id = active.route_id
                 AND requested.direction_id = active.direction_id
                GROUP BY active.origin_stop_id, active.destination_stop_id,
                         active.route_id, active.direction_id,
                         active.departure_date, active.slot_index
            ),
            candidates AS (
                SELECT * FROM physical
                UNION ALL
                SELECT * FROM service
            )
            SELECT scope, origin_stop_id, destination_stop_id,
                   route_id, direction_id,
                   ARRAY_AGG(departure_date ORDER BY departure_date, slot_index)
                       AS departure_dates,
                   ARRAY_AGG(slot_index ORDER BY departure_date, slot_index)
                       AS slot_indexes,
                   ARRAY_AGG(mean_duration_seconds ORDER BY departure_date, slot_index)
                       AS mean_duration_seconds,
                   ARRAY_AGG(trip_count ORDER BY departure_date, slot_index)
                       AS trip_counts
            FROM candidates
            GROUP BY scope, origin_stop_id, destination_stop_id,
                     route_id, direction_id
            """
        ),
        {
            "pairs": json.dumps(requested_pairs),
            "dates": json.dumps(requested_dates),
            "services": json.dumps(
                [
                    {
                        "origin_stop_id": request.origin_stop_id,
                        "destination_stop_id": request.destination_stop_id,
                        "route_id": request.route_id,
                        "direction_id": request.direction_id,
                    }
                    for request in unique_requests
                ]
            ),
        },
    )
    planned_totals: dict[
        tuple[str, str, str, str | None, int | None, date, int], tuple[float, int]
    ] = {}
    def add_planned_group(
        key: tuple[str, str, str, str | None, int | None, date, int],
        mean_seconds: float,
        sample_count: int,
    ) -> None:
        total, count = planned_totals.get(key, (0.0, 0))
        planned_totals[key] = (
            total + mean_seconds * sample_count,
            count + sample_count,
        )

    for row in planned_result.mappings():
        for departure_date, slot_index, mean_seconds, trip_count in zip(
            row["departure_dates"],
            row["slot_indexes"],
            row["mean_duration_seconds"],
            row["trip_counts"],
            strict=True,
        ):
            key = (
                row["scope"],
                row["origin_stop_id"],
                row["destination_stop_id"],
                row["route_id"],
                row["direction_id"],
                departure_date,
                slot_index,
            )
            add_planned_group(
                key,
                float(mean_seconds),
                trip_count,
            )

    return SegmentEstimateCatalog(
        live_by_key=live_by_key,
        profiles_by_key_and_slot=profiles_by_key_and_slot,
        planned_by_scope_pair_and_slot={
            key: EstimateCandidate(
                value_seconds=total / count,
                reliability=1.0,
                sample_count=count,
            )
            for key, (total, count) in planned_totals.items()
        },
    )
