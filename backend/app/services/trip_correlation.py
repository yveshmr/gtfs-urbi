from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

_SERVICE_TIME_PATTERN = re.compile(
    r"(?<!\d)(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)


@dataclass(frozen=True, slots=True)
class TripCorrelationKey:
    line: str
    direction: str
    planned_time: str


@dataclass(frozen=True, slots=True)
class TripCorrelationResult:
    status: Literal["matched", "fallback_required"]
    reason: Literal[
        "unique_exact_match",
        "missing_input",
        "no_exact_match",
        "ambiguous_exact_match",
    ]
    trip_id: str | None
    candidate_count: int


def normalize_model4_line(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().replace(".", "")
    return normalized or None


def normalize_direction(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def normalize_service_time(value: str | None) -> str | None:
    if value is None:
        return None

    match = _SERVICE_TIME_PATTERN.search(value)
    if match is None:
        return None

    hour = int(match.group("hour"))
    minute = match.group("minute")
    second = match.group("second") or "00"
    return f"{hour:02d}:{minute}:{second}"


def correlate_exact_trip(
    *,
    line: str | None,
    direction: str | None,
    planned_time: str | None,
    candidates_by_key: Mapping[TripCorrelationKey, Sequence[str]],
) -> TripCorrelationResult:
    normalized_line = normalize_model4_line(line)
    normalized_direction = normalize_direction(direction)
    normalized_time = normalize_service_time(planned_time)

    if normalized_line is None or normalized_direction is None or normalized_time is None:
        return TripCorrelationResult(
            status="fallback_required",
            reason="missing_input",
            trip_id=None,
            candidate_count=0,
        )

    key = TripCorrelationKey(
        line=normalized_line,
        direction=normalized_direction,
        planned_time=normalized_time,
    )
    candidates = candidates_by_key.get(key, ())

    if len(candidates) == 1:
        return TripCorrelationResult(
            status="matched",
            reason="unique_exact_match",
            trip_id=candidates[0],
            candidate_count=1,
        )

    reason: Literal["no_exact_match", "ambiguous_exact_match"]
    reason = "no_exact_match" if not candidates else "ambiguous_exact_match"
    return TripCorrelationResult(
        status="fallback_required",
        reason=reason,
        trip_id=None,
        candidate_count=len(candidates),
    )
