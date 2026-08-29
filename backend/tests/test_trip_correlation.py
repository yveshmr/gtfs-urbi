import pytest
from app.services.trip_correlation import (
    TripCorrelationKey,
    correlate_exact_trip,
    normalize_model4_line,
    normalize_service_time,
)


@pytest.mark.parametrize(
    ("model4_line", "gtfs_line"),
    [
        ("0.038", "0038"),
        ("0.0841", "00841"),
        (" 0.340 ", "0340"),
    ],
)
def test_normalize_model4_line(model4_line: str, gtfs_line: str) -> None:
    assert normalize_model4_line(model4_line) == gtfs_line


def test_normalize_service_time_accepts_time_inside_datetime() -> None:
    assert normalize_service_time("28/08/2026 04:05:00") == "04:05:00"


def test_unique_exact_candidate_is_high_confidence_match() -> None:
    key = TripCorrelationKey("0038", "1", "04:05:00")

    result = correlate_exact_trip(
        line="0.038",
        direction="1",
        planned_time="04:05:00",
        candidates_by_key={key: ["trip-1"]},
    )

    assert result.status == "matched"
    assert result.reason == "unique_exact_match"
    assert result.trip_id == "trip-1"
    assert result.candidate_count == 1


@pytest.mark.parametrize(
    ("line", "direction", "planned_time"),
    [
        (None, "1", "04:05:00"),
        ("0.038", None, "04:05:00"),
        ("0.038", "1", None),
    ],
)
def test_missing_input_requires_fallback(
    line: str | None,
    direction: str | None,
    planned_time: str | None,
) -> None:
    result = correlate_exact_trip(
        line=line,
        direction=direction,
        planned_time=planned_time,
        candidates_by_key={},
    )

    assert result.status == "fallback_required"
    assert result.reason == "missing_input"
    assert result.trip_id is None


def test_no_exact_candidate_requires_fallback_without_time_tolerance() -> None:
    candidate = TripCorrelationKey("0038", "1", "04:16:00")

    result = correlate_exact_trip(
        line="0.038",
        direction="1",
        planned_time="04:05:00",
        candidates_by_key={candidate: ["trip-1"]},
    )

    assert result.status == "fallback_required"
    assert result.reason == "no_exact_match"
    assert result.candidate_count == 0


def test_ambiguous_exact_candidates_require_fallback() -> None:
    key = TripCorrelationKey("0038", "1", "04:05:00")

    result = correlate_exact_trip(
        line="0.038",
        direction="1",
        planned_time="04:05:00",
        candidates_by_key={key: ["trip-1", "trip-2"]},
    )

    assert result.status == "fallback_required"
    assert result.reason == "ambiguous_exact_match"
    assert result.trip_id is None
    assert result.candidate_count == 2
