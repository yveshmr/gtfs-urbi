from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class HistoricalProfileRefreshResult:
    performed: bool
    profiles_updated: int
    reference_start_date: date
    reference_end_date: date


async def refresh_historical_profiles_if_due(
    session: AsyncSession,
    *,
    current_service_date: date,
) -> HistoricalProfileRefreshResult:
    reference_start = current_service_date - timedelta(days=7)
    reference_end = current_service_date - timedelta(days=1)
    updated_at = datetime.now(UTC)
    claim = await session.execute(
        text(
            """
            INSERT INTO analytics.segment_profile_refresh_state (
                profile_name, reference_start_date, reference_end_date, updated_at
            ) VALUES (
                'rolling_7_days', :reference_start, :reference_end, :updated_at
            )
            ON CONFLICT (profile_name) DO UPDATE SET
                reference_start_date = EXCLUDED.reference_start_date,
                reference_end_date = EXCLUDED.reference_end_date,
                updated_at = EXCLUDED.updated_at
            WHERE segment_profile_refresh_state.reference_end_date
                < EXCLUDED.reference_end_date
            RETURNING profile_name
            """
        ),
        {
            "reference_start": reference_start,
            "reference_end": reference_end,
            "updated_at": updated_at,
        },
    )
    if not list(claim.mappings()):
        return HistoricalProfileRefreshResult(
            performed=False,
            profiles_updated=0,
            reference_start_date=reference_start,
            reference_end_date=reference_end,
        )

    result = await session.execute(
        text(
            """
            WITH eligible AS (
                SELECT *
                FROM analytics.segment_daily_metrics_5m
                WHERE service_date BETWEEN :reference_start AND :reference_end
            ),
            weighted_means AS (
                SELECT
                    metric_key,
                    day_type,
                    slot_index,
                    SUM(mean_seconds * accepted_weight)
                        / NULLIF(SUM(accepted_weight), 0) AS weighted_mean
                FROM eligible
                GROUP BY metric_key, day_type, slot_index
            ),
            combined AS (
                SELECT
                    daily.metric_key,
                    daily.day_type,
                    daily.slot_index,
                    MAX(daily.scope) AS scope,
                    MAX(daily.origin_stop_id) AS origin_stop_id,
                    MAX(daily.destination_stop_id) AS destination_stop_id,
                    MAX(daily.route_id) AS route_id,
                    MAX(daily.direction_id) AS direction_id,
                    (ARRAY_AGG(
                        daily.source_feed_id
                        ORDER BY daily.last_completed_at DESC
                    ))[1] AS last_source_feed_id,
                    SUM(daily.sample_count_total)::integer AS sample_count_total,
                    SUM(daily.sample_count_accepted)::integer
                        AS sample_count_accepted,
                    SUM(daily.sample_count_rejected)::integer
                        AS sample_count_rejected,
                    SUM(daily.accepted_weight) AS accepted_weight,
                    means.weighted_mean AS mean_seconds,
                    SUM(
                        daily.m2_seconds
                        + daily.accepted_weight
                          * POWER(daily.mean_seconds - means.weighted_mean, 2)
                    ) FILTER (WHERE daily.mean_seconds IS NOT NULL) AS m2_seconds,
                    MIN(daily.minimum_seconds) AS minimum_seconds,
                    MAX(daily.maximum_seconds) AS maximum_seconds,
                    MAX(daily.last_completed_at) AS last_completed_at
                FROM eligible AS daily
                JOIN weighted_means AS means
                  ON means.metric_key = daily.metric_key
                 AND means.day_type = daily.day_type
                 AND means.slot_index = daily.slot_index
                GROUP BY daily.metric_key, daily.day_type, daily.slot_index,
                         means.weighted_mean
            )
            INSERT INTO analytics.segment_profiles_5m (
                metric_key, day_type, slot_index, reference_start_date,
                reference_end_date, scope, origin_stop_id, destination_stop_id,
                route_id, direction_id, last_source_feed_id,
                sample_count_total, sample_count_accepted,
                sample_count_rejected, accepted_weight, mean_seconds,
                m2_seconds, standard_deviation_seconds, median_seconds,
                mad_seconds, ewma_seconds, minimum_seconds, maximum_seconds,
                reliability, last_completed_at, updated_at
            )
            SELECT
                metric_key, day_type, slot_index, :reference_start,
                :reference_end, scope, origin_stop_id, destination_stop_id,
                route_id, direction_id, last_source_feed_id,
                sample_count_total, sample_count_accepted,
                sample_count_rejected, accepted_weight, mean_seconds,
                COALESCE(m2_seconds, 0),
                CASE
                    WHEN accepted_weight > 0
                    THEN SQRT(COALESCE(m2_seconds, 0) / accepted_weight)
                END,
                NULL, NULL, NULL, minimum_seconds, maximum_seconds,
                LEAST(1.0, accepted_weight / 5.0)
                    * sample_count_accepted::double precision
                    / sample_count_total,
                last_completed_at, :updated_at
            FROM combined
            ON CONFLICT (metric_key, day_type, slot_index) DO UPDATE SET
                reference_start_date = EXCLUDED.reference_start_date,
                reference_end_date = EXCLUDED.reference_end_date,
                scope = EXCLUDED.scope,
                origin_stop_id = EXCLUDED.origin_stop_id,
                destination_stop_id = EXCLUDED.destination_stop_id,
                route_id = EXCLUDED.route_id,
                direction_id = EXCLUDED.direction_id,
                last_source_feed_id = EXCLUDED.last_source_feed_id,
                sample_count_total = EXCLUDED.sample_count_total,
                sample_count_accepted = EXCLUDED.sample_count_accepted,
                sample_count_rejected = EXCLUDED.sample_count_rejected,
                accepted_weight = EXCLUDED.accepted_weight,
                mean_seconds = EXCLUDED.mean_seconds,
                m2_seconds = EXCLUDED.m2_seconds,
                standard_deviation_seconds = EXCLUDED.standard_deviation_seconds,
                median_seconds = EXCLUDED.median_seconds,
                mad_seconds = EXCLUDED.mad_seconds,
                ewma_seconds = EXCLUDED.ewma_seconds,
                minimum_seconds = EXCLUDED.minimum_seconds,
                maximum_seconds = EXCLUDED.maximum_seconds,
                reliability = EXCLUDED.reliability,
                last_completed_at = EXCLUDED.last_completed_at,
                updated_at = EXCLUDED.updated_at
            RETURNING metric_key
            """
        ),
        {
            "reference_start": reference_start,
            "reference_end": reference_end,
            "updated_at": updated_at,
        },
    )
    return HistoricalProfileRefreshResult(
        performed=True,
        profiles_updated=len(list(result.mappings())),
        reference_start_date=reference_start,
        reference_end_date=reference_end,
    )
