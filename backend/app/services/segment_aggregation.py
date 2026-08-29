from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

MetricScope = Literal["physical", "service"]
DayType = Literal["weekday", "saturday", "sunday"]
EstimateSource = Literal["live", "historical", "gtfs_planned", "unavailable"]
_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_WINDOW_SIZE = timedelta(minutes=5)
_LIVE_MAX_AGE = timedelta(hours=1)
_HISTORICAL_LOOKBACK = timedelta(days=7)
FALLBACK_SLOT_OFFSETS_MINUTES = (
    0,
    -5,
    5,
    -10,
    10,
    -15,
    15,
    -20,
    20,
    -25,
    25,
    -30,
    30,
)


@dataclass(frozen=True, slots=True)
class SegmentMetricIdentity:
    scope: MetricScope
    origin_stop_id: str
    destination_stop_id: str
    route_id: str | None = None
    direction_id: int | None = None

    def __post_init__(self) -> None:
        if not self.origin_stop_id or not self.destination_stop_id:
            raise ValueError("Segment stops cannot be empty.")
        if self.origin_stop_id == self.destination_stop_id:
            raise ValueError("Segment stops must be different.")
        if self.scope == "physical":
            if self.route_id is not None or self.direction_id is not None:
                raise ValueError("Physical metrics cannot contain service dimensions.")
        elif self.scope == "service":
            if not self.route_id or self.direction_id is None:
                raise ValueError("Service metrics require route and direction.")
        else:
            raise ValueError(f"Unsupported metric scope: {self.scope}")

    @property
    def metric_key(self) -> str:
        canonical = json.dumps(
            {
                "destination_stop_id": self.destination_stop_id,
                "direction_id": self.direction_id,
                "origin_stop_id": self.origin_stop_id,
                "route_id": self.route_id,
                "scope": self.scope,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SegmentCompletionSample:
    completed_at: datetime
    duration_seconds: float
    accepted: bool
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class SegmentWindowStatistics:
    window_start: datetime
    window_end: datetime
    sample_count_total: int
    sample_count_accepted: int
    sample_count_rejected: int
    accepted_weight: float
    mean_seconds: float | None
    median_seconds: float | None
    standard_deviation_seconds: float | None
    minimum_seconds: float | None
    maximum_seconds: float | None
    m2_seconds: float
    last_completed_at: datetime

    @property
    def acceptance_ratio(self) -> float:
        return self.sample_count_accepted / self.sample_count_total


@dataclass(frozen=True, slots=True)
class RunningMoments:
    count: int
    weight_sum: float
    mean: float | None
    m2: float
    standard_deviation: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class EstimateCandidate:
    value_seconds: float
    reliability: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class LiveEstimateCandidate(EstimateCandidate):
    window_end: datetime


@dataclass(frozen=True, slots=True)
class HistoricalEstimateCandidate(EstimateCandidate):
    slot_offset_minutes: int

    def __post_init__(self) -> None:
        if abs(self.slot_offset_minutes) > 30:
            raise ValueError("Historical slot offset must be between -30 and 30 minutes.")
        if self.slot_offset_minutes % 5:
            raise ValueError("Historical slot offset must use five-minute increments.")


@dataclass(frozen=True, slots=True)
class ResolvedSegmentEstimate:
    value_seconds: float | None
    reliability: float
    sample_count: int
    source: EstimateSource
    age_seconds: float | None
    historical_offset_minutes: int | None


def metric_identities_for_segment(
    *,
    origin_stop_id: str,
    destination_stop_id: str,
    route_id: str,
    direction_id: int,
) -> tuple[SegmentMetricIdentity, SegmentMetricIdentity]:
    return (
        SegmentMetricIdentity(
            scope="physical",
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
        ),
        SegmentMetricIdentity(
            scope="service",
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
        ),
    )


def five_minute_window(timestamp: datetime) -> tuple[datetime, datetime]:
    if timestamp.tzinfo is None:
        raise ValueError("Window timestamps must include a timezone.")
    local = timestamp.astimezone(_OPERATIONAL_TIMEZONE)
    start = local.replace(
        minute=local.minute - local.minute % 5,
        second=0,
        microsecond=0,
    )
    return start, start + _WINDOW_SIZE


def operational_day_type(timestamp: datetime) -> DayType:
    if timestamp.tzinfo is None:
        raise ValueError("Day type timestamps must include a timezone.")
    weekday = timestamp.astimezone(_OPERATIONAL_TIMEZONE).isoweekday()
    if weekday == 6:
        return "saturday"
    if weekday == 7:
        return "sunday"
    return "weekday"


def operational_service_date(timestamp: datetime) -> date:
    if timestamp.tzinfo is None:
        raise ValueError("Service-date timestamps must include a timezone.")
    return timestamp.astimezone(_OPERATIONAL_TIMEZONE).date()


def profile_slot(timestamp: datetime) -> tuple[DayType, int]:
    window_start, _ = five_minute_window(timestamp)
    slot_index = (window_start.hour * 60 + window_start.minute) // 5
    return operational_day_type(window_start), slot_index


def historical_profile_slots(timestamp: datetime) -> tuple[tuple[DayType, int, int], ...]:
    return tuple(
        (*profile_slot(timestamp + timedelta(minutes=offset)), offset)
        for offset in FALLBACK_SLOT_OFFSETS_MINUTES
    )


def historical_retention_start(current_service_date: date) -> date:
    return current_service_date - _HISTORICAL_LOOKBACK


def resolve_segment_estimate(
    *,
    now: datetime,
    live: LiveEstimateCandidate | None,
    historical: tuple[HistoricalEstimateCandidate, ...],
    gtfs_planned: EstimateCandidate | None,
) -> ResolvedSegmentEstimate:
    if now.tzinfo is None:
        raise ValueError("Estimate timestamps must include a timezone.")

    if live is not None:
        if live.window_end.tzinfo is None:
            raise ValueError("Live window timestamps must include a timezone.")
        age = max(now - live.window_end, timedelta()).total_seconds()
        if age <= _LIVE_MAX_AGE.total_seconds():
            return ResolvedSegmentEstimate(
                value_seconds=live.value_seconds,
                reliability=live.reliability,
                sample_count=live.sample_count,
                source="live",
                age_seconds=age,
                historical_offset_minutes=None,
            )

    if historical:
        selected_historical = min(
            historical,
            key=lambda candidate: (
                abs(candidate.slot_offset_minutes),
                candidate.slot_offset_minutes > 0,
            ),
        )
        return ResolvedSegmentEstimate(
            value_seconds=selected_historical.value_seconds,
            reliability=selected_historical.reliability,
            sample_count=selected_historical.sample_count,
            source="historical",
            age_seconds=None,
            historical_offset_minutes=selected_historical.slot_offset_minutes,
        )

    if gtfs_planned is not None:
        return ResolvedSegmentEstimate(
            value_seconds=gtfs_planned.value_seconds,
            reliability=gtfs_planned.reliability,
            sample_count=gtfs_planned.sample_count,
            source="gtfs_planned",
            age_seconds=None,
            historical_offset_minutes=None,
        )

    return ResolvedSegmentEstimate(
        value_seconds=None,
        reliability=0.0,
        sample_count=0,
        source="unavailable",
        age_seconds=None,
        historical_offset_minutes=None,
    )


def aggregate_window(samples: list[SegmentCompletionSample]) -> SegmentWindowStatistics:
    if not samples:
        raise ValueError("At least one segment completion sample is required.")

    window_start, window_end = five_minute_window(samples[0].completed_at)
    if any(five_minute_window(sample.completed_at)[0] != window_start for sample in samples):
        raise ValueError("All samples must belong to the same five-minute window.")

    accepted_samples = [
        sample
        for sample in samples
        if sample.accepted
        and math.isfinite(sample.duration_seconds)
        and math.isfinite(sample.weight)
        and sample.weight > 0
    ]
    accepted_values = [sample.duration_seconds for sample in accepted_samples]
    accepted_weight = sum(sample.weight for sample in accepted_samples)
    accepted_count = len(accepted_values)
    total_count = len(samples)
    mean = (
        sum(sample.duration_seconds * sample.weight for sample in accepted_samples)
        / accepted_weight
        if accepted_weight
        else None
    )
    m2 = (
        sum(sample.weight * (sample.duration_seconds - mean) ** 2 for sample in accepted_samples)
        if mean is not None
        else 0.0
    )
    standard_deviation = math.sqrt(m2 / accepted_weight) if accepted_weight > 0 else None

    return SegmentWindowStatistics(
        window_start=window_start,
        window_end=window_end,
        sample_count_total=total_count,
        sample_count_accepted=accepted_count,
        sample_count_rejected=total_count - accepted_count,
        accepted_weight=accepted_weight,
        mean_seconds=mean,
        median_seconds=statistics.median(accepted_values) if accepted_values else None,
        standard_deviation_seconds=standard_deviation,
        minimum_seconds=min(accepted_values) if accepted_values else None,
        maximum_seconds=max(accepted_values) if accepted_values else None,
        m2_seconds=m2,
        last_completed_at=max(sample.completed_at for sample in samples),
    )


def merge_running_moments(
    previous: RunningMoments,
    current: SegmentWindowStatistics,
) -> RunningMoments:
    current_count = current.sample_count_accepted
    current_weight = current.accepted_weight
    if current_count == 0 or current_weight == 0 or current.mean_seconds is None:
        return previous
    if previous.count == 0 or previous.weight_sum == 0 or previous.mean is None:
        return RunningMoments(
            count=current_count,
            weight_sum=current_weight,
            mean=current.mean_seconds,
            m2=current.m2_seconds,
            standard_deviation=current.standard_deviation_seconds,
            minimum=current.minimum_seconds,
            maximum=current.maximum_seconds,
        )

    combined_count = previous.count + current_count
    combined_weight = previous.weight_sum + current_weight
    delta = current.mean_seconds - previous.mean
    combined_mean = previous.mean + delta * current_weight / combined_weight
    combined_m2 = (
        previous.m2
        + current.m2_seconds
        + delta**2 * previous.weight_sum * current_weight / combined_weight
    )
    return RunningMoments(
        count=combined_count,
        weight_sum=combined_weight,
        mean=combined_mean,
        m2=combined_m2,
        standard_deviation=(
            math.sqrt(combined_m2 / combined_weight) if combined_weight > 0 else None
        ),
        minimum=_optional_min(previous.minimum, current.minimum_seconds),
        maximum=_optional_max(previous.maximum, current.maximum_seconds),
    )


def metric_reliability(statistics_: SegmentWindowStatistics) -> float:
    sufficiency = min(1.0, statistics_.accepted_weight / 5.0)
    return sufficiency * statistics_.acceptance_ratio


def metric_status(statistics_: SegmentWindowStatistics) -> str:
    if (
        statistics_.sample_count_total >= 3
        and statistics_.sample_count_rejected / statistics_.sample_count_total >= 0.5
    ):
        return "anomalous"
    if statistics_.sample_count_accepted == 0:
        return "insufficient"

    reliability = metric_reliability(statistics_)
    if reliability < 0.4:
        return "low"
    if reliability < 0.8:
        return "medium"
    return "high"


def _optional_min(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _optional_max(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None
