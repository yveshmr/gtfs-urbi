from datetime import UTC, datetime, timedelta

import pytest
from app.services.segment_aggregation import (
    EstimateCandidate,
    HistoricalEstimateCandidate,
    LiveEstimateCandidate,
    RunningMoments,
    SegmentCompletionSample,
    SegmentMetricIdentity,
    aggregate_window,
    five_minute_window,
    historical_profile_slots,
    historical_retention_start,
    merge_running_moments,
    metric_identities_for_segment,
    metric_reliability,
    metric_status,
    operational_day_type,
    operational_service_date,
    profile_slot,
    resolve_segment_estimate,
)


def test_metric_identity_is_stable_and_separates_physical_from_service() -> None:
    physical, service = metric_identities_for_segment(
        origin_stop_id="A",
        destination_stop_id="B",
        route_id="R1",
        direction_id=1,
    )

    assert physical.scope == "physical"
    assert physical.route_id is None
    assert service.scope == "service"
    assert physical.metric_key != service.metric_key
    assert (
        physical.metric_key
        == SegmentMetricIdentity(
            scope="physical",
            origin_stop_id="A",
            destination_stop_id="B",
        ).metric_key
    )


def test_service_identity_requires_route_and_direction() -> None:
    with pytest.raises(ValueError, match="require route and direction"):
        SegmentMetricIdentity(
            scope="service",
            origin_stop_id="A",
            destination_stop_id="B",
        )


def test_five_minute_window_and_profile_slot_use_operational_timezone() -> None:
    timestamp = datetime(2026, 8, 28, 13, 7, 42, tzinfo=UTC)

    start, end = five_minute_window(timestamp)

    assert start.isoformat() == "2026-08-28T10:05:00-03:00"
    assert end.isoformat() == "2026-08-28T10:10:00-03:00"
    assert profile_slot(timestamp) == ("weekday", 121)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (datetime(2026, 8, 28, 13, tzinfo=UTC), "weekday"),
        (datetime(2026, 8, 29, 13, tzinfo=UTC), "saturday"),
        (datetime(2026, 8, 30, 13, tzinfo=UTC), "sunday"),
    ],
)
def test_operational_day_type_uses_local_calendar(
    timestamp: datetime,
    expected: str,
) -> None:
    assert operational_day_type(timestamp) == expected


def test_operational_service_date_uses_sao_paulo_timezone() -> None:
    timestamp = datetime(2026, 8, 29, 1, tzinfo=UTC)

    assert operational_service_date(timestamp).isoformat() == "2026-08-28"


def test_historical_search_uses_nearest_slots_in_both_directions() -> None:
    timestamp = datetime(2026, 8, 28, 13, 7, tzinfo=UTC)

    assert historical_profile_slots(timestamp) == (
        ("weekday", 121, 0),
        ("weekday", 120, -5),
        ("weekday", 122, 5),
        ("weekday", 119, -10),
        ("weekday", 123, 10),
        ("weekday", 118, -15),
        ("weekday", 124, 15),
        ("weekday", 117, -20),
        ("weekday", 125, 20),
        ("weekday", 116, -25),
        ("weekday", 126, 25),
        ("weekday", 115, -30),
        ("weekday", 127, 30),
    )


def test_historical_search_changes_day_type_when_crossing_midnight() -> None:
    timestamp = datetime(2026, 8, 29, 2, 52, tzinfo=UTC)

    slots = historical_profile_slots(timestamp)

    assert slots[0] == ("weekday", 286, 0)
    assert slots[4] == ("saturday", 0, 10)
    assert slots[-1] == ("saturday", 4, 30)


def test_historical_retention_keeps_the_seven_previous_service_dates() -> None:
    assert historical_retention_start(datetime(2026, 8, 29).date()).isoformat() == ("2026-08-22")


def test_aggregate_window_uses_only_accepted_finite_samples() -> None:
    samples = [
        SegmentCompletionSample(datetime(2026, 8, 28, 13, 1, tzinfo=UTC), 100, True),
        SegmentCompletionSample(datetime(2026, 8, 28, 13, 2, tzinfo=UTC), 140, True),
        SegmentCompletionSample(datetime(2026, 8, 28, 13, 3, tzinfo=UTC), 900, False),
        SegmentCompletionSample(
            datetime(2026, 8, 28, 13, 4, tzinfo=UTC),
            float("nan"),
            True,
        ),
    ]

    result = aggregate_window(samples)

    assert result.sample_count_total == 4
    assert result.sample_count_accepted == 2
    assert result.sample_count_rejected == 2
    assert result.accepted_weight == 2
    assert result.mean_seconds == 120
    assert result.median_seconds == 120
    assert result.standard_deviation_seconds == 20
    assert result.m2_seconds == 800
    assert result.minimum_seconds == 100
    assert result.maximum_seconds == 140
    assert result.acceptance_ratio == 0.5


def test_aggregate_window_rejects_mixed_windows() -> None:
    with pytest.raises(ValueError, match="same five-minute window"):
        aggregate_window(
            [
                SegmentCompletionSample(datetime(2026, 8, 28, 13, 4, tzinfo=UTC), 100, True),
                SegmentCompletionSample(datetime(2026, 8, 28, 13, 5, tzinfo=UTC), 110, True),
            ]
        )


def test_running_moments_merge_windows_without_individual_history() -> None:
    previous = RunningMoments(
        count=2,
        weight_sum=2,
        mean=110,
        m2=200,
        standard_deviation=pytest.approx(14.142135),
        minimum=100,
        maximum=120,
    )
    current = aggregate_window(
        [
            SegmentCompletionSample(datetime(2026, 8, 28, 13, 1, tzinfo=UTC), 130, True),
            SegmentCompletionSample(datetime(2026, 8, 28, 13, 2, tzinfo=UTC), 140, True),
        ]
    )

    merged = merge_running_moments(previous, current)

    assert merged.count == 4
    assert merged.weight_sum == 4
    assert merged.mean == 122.5
    assert merged.m2 == 875
    assert merged.standard_deviation == pytest.approx(14.790199)
    assert merged.minimum == 100
    assert merged.maximum == 140


def test_weighted_window_mean_uses_confirmed_confidence_weights() -> None:
    samples = [
        SegmentCompletionSample(datetime(2026, 8, 28, 13, 1, tzinfo=UTC), 100, True, 1),
        SegmentCompletionSample(datetime(2026, 8, 28, 13, 2, tzinfo=UTC), 200, True, 0.5),
    ]

    result = aggregate_window(samples)

    assert result.accepted_weight == 1.5
    assert result.mean_seconds == pytest.approx(133.333333)


def test_historical_moments_weight_days_by_accepted_evidence() -> None:
    first_day = aggregate_window(
        [SegmentCompletionSample(datetime(2026, 8, 27, 13, tzinfo=UTC), 100, True, 1)]
    )
    second_day = aggregate_window(
        [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 200, True, 0.5)]
    )
    running = RunningMoments(
        count=first_day.sample_count_accepted,
        weight_sum=first_day.accepted_weight,
        mean=first_day.mean_seconds,
        m2=first_day.m2_seconds,
        standard_deviation=first_day.standard_deviation_seconds,
        minimum=first_day.minimum_seconds,
        maximum=first_day.maximum_seconds,
    )

    combined = merge_running_moments(running, second_day)

    assert combined.count == 2
    assert combined.weight_sum == 1.5
    assert combined.mean == pytest.approx(133.333333)


@pytest.mark.parametrize(
    ("samples", "expected_reliability", "expected_status"),
    [
        (
            [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 100, False, 0)],
            0,
            "insufficient",
        ),
        (
            [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 100, True, 0.5)],
            0.1,
            "low",
        ),
        (
            [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 100, True, 1)] * 2,
            0.4,
            "medium",
        ),
        (
            [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 100, True, 1)] * 4,
            0.8,
            "high",
        ),
        (
            [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 100, True, 1)]
            + [SegmentCompletionSample(datetime(2026, 8, 28, 13, tzinfo=UTC), 900, False, 0)] * 2,
            pytest.approx(1 / 15),
            "anomalous",
        ),
    ],
)
def test_metric_reliability_and_status_thresholds(
    samples: list[SegmentCompletionSample],
    expected_reliability: float,
    expected_status: str,
) -> None:
    result = aggregate_window(samples)

    assert metric_reliability(result) == expected_reliability
    assert metric_status(result) == expected_status


def test_live_estimate_is_used_for_up_to_one_hour() -> None:
    now = datetime(2026, 8, 28, 14, tzinfo=UTC)

    result = resolve_segment_estimate(
        now=now,
        live=LiveEstimateCandidate(
            value_seconds=180,
            reliability=0.8,
            sample_count=3,
            window_end=now - timedelta(hours=1),
        ),
        historical=(HistoricalEstimateCandidate(200, 0.7, 30, 0),),
        gtfs_planned=EstimateCandidate(240, 0.4, 1),
    )

    assert result.source == "live"
    assert result.value_seconds == 180
    assert result.age_seconds == 3600


def test_expired_live_estimate_falls_back_to_same_day_type_history() -> None:
    now = datetime(2026, 8, 28, 14, tzinfo=UTC)

    result = resolve_segment_estimate(
        now=now,
        live=LiveEstimateCandidate(
            value_seconds=180,
            reliability=0.8,
            sample_count=3,
            window_end=now - timedelta(hours=1, seconds=1),
        ),
        historical=(HistoricalEstimateCandidate(200, 0.7, 30, 0),),
        gtfs_planned=EstimateCandidate(240, 0.4, 1),
    )

    assert result.source == "historical"
    assert result.value_seconds == 200
    assert result.historical_offset_minutes == 0


def test_nearest_available_historical_slot_is_selected_with_past_tie_break() -> None:
    result = resolve_segment_estimate(
        now=datetime(2026, 8, 28, 14, tzinfo=UTC),
        live=None,
        historical=(
            HistoricalEstimateCandidate(230, 0.6, 12, 30),
            HistoricalEstimateCandidate(210, 0.7, 18, 10),
            HistoricalEstimateCandidate(205, 0.75, 20, -10),
        ),
        gtfs_planned=EstimateCandidate(240, 0.4, 1),
    )

    assert result.source == "historical"
    assert result.value_seconds == 205
    assert result.historical_offset_minutes == -10


def test_gtfs_is_used_only_without_fresh_live_or_historical_estimate() -> None:
    result = resolve_segment_estimate(
        now=datetime(2026, 8, 28, 14, tzinfo=UTC),
        live=None,
        historical=(),
        gtfs_planned=EstimateCandidate(240, 0.4, 1),
    )

    assert result.source == "gtfs_planned"
    assert result.value_seconds == 240
