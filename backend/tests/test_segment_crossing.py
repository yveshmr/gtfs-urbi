from datetime import UTC, datetime, timedelta

import pytest
from app.services.segment_crossing import (
    BoundaryCrossing,
    SegmentBoundary,
    complete_segments_from_crossings,
    interpolate_crossed_boundaries,
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def test_interpolates_each_crossed_boundary_by_shape_progress() -> None:
    crossings = interpolate_crossed_boundaries(
        previous_timestamp=NOW,
        current_timestamp=NOW + timedelta(seconds=40),
        previous_progress_m=100,
        current_progress_m=300,
        boundaries=(
            SegmentBoundary("B", 2, 1, 150, "valid"),
            SegmentBoundary("C", 3, 2, 250, "valid"),
            SegmentBoundary("D", 4, 3, 350, "valid"),
        ),
    )

    assert [crossing.stop_id for crossing in crossings] == ["B", "C"]
    assert crossings[0].crossed_at == NOW + timedelta(seconds=10)
    assert crossings[1].crossed_at == NOW + timedelta(seconds=30)


def test_segment_between_separately_observed_boundaries_has_high_confidence() -> None:
    origin = BoundaryCrossing("A", 1, None, 100, "valid", NOW, NOW)
    destination = BoundaryCrossing(
        "B",
        2,
        1,
        200,
        "valid",
        NOW + timedelta(seconds=50),
        NOW + timedelta(seconds=60),
    )

    completed, last_boundary = complete_segments_from_crossings(
        last_boundary=origin,
        crossings=(destination,),
    )

    assert len(completed) == 1
    assert completed[0].duration_seconds == 50
    assert completed[0].distance_m == 100
    assert completed[0].average_speed_kmh == pytest.approx(7.2)
    assert completed[0].confidence == "high"
    assert last_boundary == destination


def test_multiple_boundaries_in_same_observation_have_reduced_confidence() -> None:
    crossings = (
        BoundaryCrossing(
            "A", 1, None, 100, "valid", NOW + timedelta(seconds=10), NOW + timedelta(seconds=30)
        ),
        BoundaryCrossing(
            "B", 2, 1, 200, "valid", NOW + timedelta(seconds=20), NOW + timedelta(seconds=30)
        ),
    )

    completed, _ = complete_segments_from_crossings(
        last_boundary=None,
        crossings=crossings,
    )

    assert len(completed) == 1
    assert completed[0].duration_seconds == 10
    assert completed[0].confidence == "reduced"


def test_reverse_or_stationary_progress_does_not_cross_a_boundary() -> None:
    crossings = interpolate_crossed_boundaries(
        previous_timestamp=NOW,
        current_timestamp=NOW + timedelta(seconds=10),
        previous_progress_m=200,
        current_progress_m=195,
        boundaries=(SegmentBoundary("B", 2, 1, 198, "valid"),),
    )

    assert crossings == ()


def test_fallback_boundary_breaks_segment_completion_chain() -> None:
    origin = BoundaryCrossing("A", 1, None, 100, "valid", NOW, NOW)
    fallback = BoundaryCrossing(
        "B", 2, 1, 200, "fallback_required", NOW + timedelta(seconds=10), NOW
    )
    destination = BoundaryCrossing(
        "C", 3, 2, 300, "valid", NOW + timedelta(seconds=20), NOW + timedelta(seconds=30)
    )

    completed, last_boundary = complete_segments_from_crossings(
        last_boundary=origin,
        crossings=(fallback, destination),
    )

    assert completed == ()
    assert last_boundary == destination
