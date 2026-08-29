from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

CrossingConfidence = Literal["high", "reduced"]
BoundaryQuality = Literal["valid", "reduced", "fallback_required"]


@dataclass(frozen=True, slots=True)
class SegmentBoundary:
    stop_id: str
    stop_sequence: int
    previous_stop_sequence: int | None
    progress_m: float
    projection_quality: BoundaryQuality


@dataclass(frozen=True, slots=True)
class BoundaryCrossing:
    stop_id: str
    stop_sequence: int
    previous_stop_sequence: int | None
    progress_m: float
    projection_quality: BoundaryQuality
    crossed_at: datetime
    observation_end: datetime


@dataclass(frozen=True, slots=True)
class CompletedSegment:
    origin_stop_id: str
    destination_stop_id: str
    origin_stop_sequence: int
    destination_stop_sequence: int
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    distance_m: float
    confidence: CrossingConfidence

    @property
    def average_speed_kmh(self) -> float:
        return self.distance_m / self.duration_seconds * 3.6


def interpolate_crossed_boundaries(
    *,
    previous_timestamp: datetime,
    current_timestamp: datetime,
    previous_progress_m: float,
    current_progress_m: float,
    boundaries: tuple[SegmentBoundary, ...],
) -> tuple[BoundaryCrossing, ...]:
    if previous_timestamp.tzinfo is None or current_timestamp.tzinfo is None:
        raise ValueError("Observation timestamps must include a timezone.")
    if current_timestamp <= previous_timestamp:
        return ()
    if current_progress_m <= previous_progress_m:
        return ()

    elapsed = current_timestamp - previous_timestamp
    progress_delta = current_progress_m - previous_progress_m
    crossed: list[BoundaryCrossing] = []
    for boundary in sorted(boundaries, key=lambda item: item.progress_m):
        if not previous_progress_m < boundary.progress_m <= current_progress_m:
            continue
        fraction = (boundary.progress_m - previous_progress_m) / progress_delta
        crossed.append(
            BoundaryCrossing(
                stop_id=boundary.stop_id,
                stop_sequence=boundary.stop_sequence,
                previous_stop_sequence=boundary.previous_stop_sequence,
                progress_m=boundary.progress_m,
                projection_quality=boundary.projection_quality,
                crossed_at=previous_timestamp + elapsed * fraction,
                observation_end=current_timestamp,
            )
        )
    return tuple(crossed)


def complete_segments_from_crossings(
    *,
    last_boundary: BoundaryCrossing | None,
    crossings: tuple[BoundaryCrossing, ...],
) -> tuple[tuple[CompletedSegment, ...], BoundaryCrossing | None]:
    completed: list[CompletedSegment] = []
    origin = last_boundary
    for destination in crossings:
        boundaries_are_adjacent = (
            origin is not None and destination.previous_stop_sequence == origin.stop_sequence
        )
        boundaries_are_usable = (
            origin is not None
            and origin.projection_quality != "fallback_required"
            and destination.projection_quality != "fallback_required"
        )
        if boundaries_are_adjacent and boundaries_are_usable:
            duration = destination.crossed_at - origin.crossed_at
            if duration > timedelta(0):
                completed.append(
                    CompletedSegment(
                        origin_stop_id=origin.stop_id,
                        destination_stop_id=destination.stop_id,
                        origin_stop_sequence=origin.stop_sequence,
                        destination_stop_sequence=destination.stop_sequence,
                        started_at=origin.crossed_at,
                        completed_at=destination.crossed_at,
                        duration_seconds=duration.total_seconds(),
                        distance_m=destination.progress_m - origin.progress_m,
                        confidence=(
                            "reduced"
                            if origin.observation_end == destination.observation_end
                            or origin.projection_quality == "reduced"
                            or destination.projection_quality == "reduced"
                            else "high"
                        ),
                    )
                )
        if origin is None or destination.stop_sequence > origin.stop_sequence:
            origin = destination
    return tuple(completed), origin
