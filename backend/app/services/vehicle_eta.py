from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.services.segment_aggregation import ResolvedSegmentEstimate

EtaScope = Literal["physical", "service"]
EtaScenario = Literal["current_time", "future_time"]


@dataclass(frozen=True, slots=True)
class RemainingTripSegment:
    origin_stop_id: str
    destination_stop_id: str
    origin_stop_sequence: int
    destination_stop_sequence: int
    remaining_fraction: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.remaining_fraction <= 1:
            raise ValueError("Remaining segment fraction must be between zero and one.")


@dataclass(frozen=True, slots=True)
class EtaTarget:
    value_seconds: float | None
    estimated_at: datetime | None
    reliability: float
    segments_covered: int
    segments_total: int
    source_counts: dict[str, int]
    complete: bool
    missing_origin_stop_id: str | None
    missing_destination_stop_id: str | None


@dataclass(frozen=True, slots=True)
class EtaProjection:
    scope: EtaScope
    scenario: EtaScenario
    next_stop: EtaTarget
    trip_end: EtaTarget


SegmentResolver = Callable[
    [RemainingTripSegment, datetime, EtaScope],
    Awaitable[ResolvedSegmentEstimate],
]


async def compose_eta_projection(
    *,
    segments: tuple[RemainingTripSegment, ...],
    queried_at: datetime,
    scope: EtaScope,
    scenario: EtaScenario,
    resolver: SegmentResolver,
) -> EtaProjection:
    if queried_at.tzinfo is None:
        raise ValueError("ETA timestamp must include a timezone.")
    if not segments:
        raise ValueError("At least one remaining segment is required.")

    total_seconds = 0.0
    weighted_reliability = 0.0
    covered = 0
    source_counts: Counter[str] = Counter()
    next_stop: EtaTarget | None = None
    missing_segment: RemainingTripSegment | None = None
    future_cursor = queried_at

    for index, segment in enumerate(segments):
        estimate_at = queried_at if scenario == "current_time" else future_cursor
        estimate = await resolver(segment, estimate_at, scope)
        if estimate.value_seconds is None or estimate.source == "unavailable":
            missing_segment = segment
            break

        duration = estimate.value_seconds * segment.remaining_fraction
        total_seconds += duration
        weighted_reliability += duration * estimate.reliability
        covered += 1
        source_counts[estimate.source] += 1
        if scenario == "future_time":
            future_cursor += timedelta(seconds=duration)

        if index == 0:
            next_stop = EtaTarget(
                value_seconds=duration,
                estimated_at=queried_at + timedelta(seconds=duration),
                reliability=estimate.reliability,
                segments_covered=1,
                segments_total=1,
                source_counts={estimate.source: 1},
                complete=True,
                missing_origin_stop_id=None,
                missing_destination_stop_id=None,
            )

    if next_stop is None:
        first = segments[0]
        next_stop = EtaTarget(
            value_seconds=None,
            estimated_at=None,
            reliability=0.0,
            segments_covered=0,
            segments_total=1,
            source_counts={},
            complete=False,
            missing_origin_stop_id=first.origin_stop_id,
            missing_destination_stop_id=first.destination_stop_id,
        )

    trip_is_complete = covered == len(segments)
    trip_end = EtaTarget(
        value_seconds=total_seconds if trip_is_complete else None,
        estimated_at=(queried_at + timedelta(seconds=total_seconds) if trip_is_complete else None),
        reliability=(weighted_reliability / total_seconds if total_seconds > 0 else 0.0),
        segments_covered=covered,
        segments_total=len(segments),
        source_counts=dict(source_counts),
        complete=trip_is_complete,
        missing_origin_stop_id=(
            missing_segment.origin_stop_id if missing_segment is not None else None
        ),
        missing_destination_stop_id=(
            missing_segment.destination_stop_id if missing_segment is not None else None
        ),
    )
    return EtaProjection(
        scope=scope,
        scenario=scenario,
        next_stop=next_stop,
        trip_end=trip_end,
    )
