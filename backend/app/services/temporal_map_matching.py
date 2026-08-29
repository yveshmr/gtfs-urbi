from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_SAMPLE_GAP = timedelta(minutes=5)
MIN_MOVEMENT_M = 20.0
MAX_DIRECTION_DIFFERENCE_DEGREES = 60.0
MAX_DISTANCE_TO_SHAPE_M = 50.0
MAX_REVERSE_JITTER_M = 15.0


@dataclass(frozen=True, slots=True)
class ShapeCandidate:
    segment_sequence: int
    progress_m: float
    shape_position: float
    distance_to_shape_m: float
    bearing_degrees: float
    projected_latitude: float
    projected_longitude: float


@dataclass(frozen=True, slots=True)
class PositionSample:
    timestamp: datetime
    latitude: float
    longitude: float
    candidates: tuple[ShapeCandidate, ...]


@dataclass(frozen=True, slots=True)
class MapMatchResult:
    status: str
    candidate: ShapeCandidate | None = None
    path: tuple[ShapeCandidate, ...] = ()


def _distance_m(first: PositionSample, last: PositionSample) -> float:
    radius_m = 6_371_008.8
    lat_1 = math.radians(first.latitude)
    lat_2 = math.radians(last.latitude)
    delta_lat = lat_2 - lat_1
    delta_lon = math.radians(last.longitude - first.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(haversine)))


def _bearing_degrees(first: PositionSample, last: PositionSample) -> float:
    lat_1 = math.radians(first.latitude)
    lat_2 = math.radians(last.latitude)
    delta_lon = math.radians(last.longitude - first.longitude)
    y = math.sin(delta_lon) * math.cos(lat_2)
    x = math.cos(lat_1) * math.sin(lat_2) - math.sin(lat_1) * math.cos(lat_2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360


def _angular_difference(first: float, second: float) -> float:
    return abs((first - second + 180) % 360 - 180)


def _eligible_candidates(
    sample: PositionSample,
    movement_bearing: float,
) -> tuple[ShapeCandidate, ...]:
    return tuple(
        candidate
        for candidate in sample.candidates
        if candidate.distance_to_shape_m <= MAX_DISTANCE_TO_SHAPE_M
        and _angular_difference(candidate.bearing_degrees, movement_bearing)
        <= MAX_DIRECTION_DIFFERENCE_DEGREES
    )


def _progress_clusters(
    candidates: tuple[ShapeCandidate, ...],
) -> list[list[ShapeCandidate]]:
    clusters: list[list[ShapeCandidate]] = []
    for candidate in sorted(candidates, key=lambda item: item.progress_m):
        separated_from_previous = (
            bool(clusters)
            and candidate.progress_m - clusters[-1][-1].progress_m > MAX_REVERSE_JITTER_M
        )
        if not clusters or separated_from_previous:
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)
    return clusters


def match_three_samples(samples: tuple[PositionSample, ...]) -> MapMatchResult:
    if samples and not samples[-1].candidates:
        return MapMatchResult("fallback_required")

    if len(samples) < 3:
        return MapMatchResult("collecting")

    window = samples[-3:]
    if any(
        current.timestamp <= previous.timestamp
        or current.timestamp - previous.timestamp > MAX_SAMPLE_GAP
        for previous, current in zip(window, window[1:], strict=False)
    ):
        return MapMatchResult("collecting")

    if _distance_m(window[0], window[-1]) < MIN_MOVEMENT_M:
        return MapMatchResult("collecting")

    movement_bearing = _bearing_degrees(window[0], window[-1])
    candidate_windows = tuple(_eligible_candidates(sample, movement_bearing) for sample in window)
    if any(not candidates for candidates in candidate_windows):
        return MapMatchResult("ambiguous")

    reachable_paths = tuple((candidate,) for candidate in candidate_windows[0])
    for candidates in candidate_windows[1:]:
        next_paths: list[tuple[ShapeCandidate, ...]] = []
        for candidate in candidates:
            predecessors = tuple(
                path
                for path in reachable_paths
                if candidate.progress_m >= path[-1].progress_m - MAX_REVERSE_JITTER_M
            )
            if predecessors:
                best_predecessor = min(
                    predecessors,
                    key=lambda path: sum(item.distance_to_shape_m for item in path),
                )
                next_paths.append((*best_predecessor, candidate))
        reachable_paths = tuple(next_paths)
        if not reachable_paths:
            return MapMatchResult("ambiguous")

    clusters = _progress_clusters(tuple(path[-1] for path in reachable_paths))
    if len(clusters) != 1:
        return MapMatchResult("ambiguous")

    selected_paths = tuple(path for path in reachable_paths if path[-1] in clusters[0])
    selected_path = min(
        selected_paths,
        key=lambda path: (
            sum(candidate.distance_to_shape_m for candidate in path),
            sum(
                _angular_difference(candidate.bearing_degrees, movement_bearing)
                for candidate in path
            ),
            path[-1].progress_m,
        ),
    )
    return MapMatchResult("resolved", selected_path[-1], selected_path)
