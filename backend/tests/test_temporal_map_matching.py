from datetime import UTC, datetime, timedelta

from app.services.temporal_map_matching import (
    PositionSample,
    ShapeCandidate,
    match_three_samples,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def candidate(progress_m: float, *, bearing: float = 90, distance: float = 5) -> ShapeCandidate:
    return ShapeCandidate(
        segment_sequence=int(progress_m),
        progress_m=progress_m,
        shape_position=progress_m / 1_000,
        distance_to_shape_m=distance,
        bearing_degrees=bearing,
        projected_latitude=0,
        projected_longitude=progress_m / 100_000,
    )


def sample(
    seconds: int,
    longitude: float,
    *candidates: ShapeCandidate,
) -> PositionSample:
    return PositionSample(
        timestamp=NOW + timedelta(seconds=seconds),
        latitude=0,
        longitude=longitude,
        candidates=candidates,
    )


def test_resolves_unique_monotonic_occurrence() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100)),
            sample(10, 0.0001, candidate(110)),
            sample(20, 0.0002, candidate(120)),
        )
    )

    assert result.status == "resolved"
    assert result.candidate is not None
    assert result.candidate.progress_m == 120
    assert [item.progress_m for item in result.path] == [100, 110, 120]


def test_history_disambiguates_repeated_location_on_shape() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(800)),
            sample(10, 0.0001, candidate(810)),
            sample(20, 0.0002, candidate(120), candidate(820)),
        )
    )

    assert result.status == "resolved"
    assert result.candidate is not None
    assert result.candidate.progress_m == 820
    assert [item.progress_m for item in result.path] == [800, 810, 820]


def test_keeps_ambiguous_when_two_monotonic_occurrences_remain() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100), candidate(800)),
            sample(10, 0.0001, candidate(110), candidate(810)),
            sample(20, 0.0002, candidate(120), candidate(820)),
        )
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_collects_until_vehicle_moves_twenty_metres() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100)),
            sample(10, 0.00001, candidate(101)),
            sample(20, 0.00002, candidate(102)),
        )
    )

    assert result.status == "collecting"


def test_rejects_direction_difference_over_sixty_degrees() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100, bearing=270)),
            sample(10, 0.0001, candidate(110, bearing=270)),
            sample(20, 0.0002, candidate(120, bearing=270)),
        )
    )

    assert result.status == "ambiguous"


def test_rejects_reverse_progress_beyond_jitter() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(140)),
            sample(10, 0.0001, candidate(120)),
            sample(20, 0.0002, candidate(100)),
        )
    )

    assert result.status == "ambiguous"


def test_accepts_source_updates_slower_than_polling_interval() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100)),
            sample(31, 0.0001, candidate(110)),
            sample(41, 0.0002, candidate(120)),
        )
    )

    assert result.status == "resolved"


def test_resets_collection_when_sample_gap_exceeds_five_minutes() -> None:
    result = match_three_samples(
        (
            sample(0, 0, candidate(100)),
            sample(301, 0.0001, candidate(110)),
            sample(311, 0.0002, candidate(120)),
        )
    )

    assert result.status == "collecting"


def test_current_position_outside_fifty_metres_requires_fallback_immediately() -> None:
    result = match_three_samples((sample(0, 0),))

    assert result.status == "fallback_required"
