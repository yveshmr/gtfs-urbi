import pytest
from app.services.segment_sample_validation import assess_segment_sample


def test_rejects_average_speed_above_80_kmh() -> None:
    result = assess_segment_sample(
        duration_seconds=10,
        distance_m=250,
        confidence="high",
        accepted_reference_durations=(),
    )

    assert result.accepted is False
    assert result.rejection_reason == "speed_over_80"
    assert result.weight == 0


def test_accepts_exactly_80_kmh_with_reduced_weight_before_five_references() -> None:
    result = assess_segment_sample(
        duration_seconds=45,
        distance_m=1000,
        confidence="high",
        accepted_reference_durations=(40, 42, 44, 46),
    )

    assert result.accepted is True
    assert result.reference_count == 4
    assert result.weight == 0.5


def test_mad_rejects_modified_z_score_above_3_5() -> None:
    result = assess_segment_sample(
        duration_seconds=140,
        distance_m=500,
        confidence="high",
        accepted_reference_durations=(58, 59, 60, 61, 62),
    )

    assert result.accepted is False
    assert result.rejection_reason == "mad_outlier"
    assert result.reference_median_seconds == 60
    assert result.reference_mad_seconds == 1
    assert result.modified_z_score == pytest.approx(53.96)


def test_high_and_reduced_crossings_receive_confirmed_weights() -> None:
    references = (58, 59, 60, 61, 62)

    high = assess_segment_sample(
        duration_seconds=63,
        distance_m=500,
        confidence="high",
        accepted_reference_durations=references,
    )
    reduced = assess_segment_sample(
        duration_seconds=63,
        distance_m=500,
        confidence="reduced",
        accepted_reference_durations=references,
    )

    assert high.accepted is True
    assert high.weight == 1
    assert reduced.accepted is True
    assert reduced.weight == 0.5


def test_zero_mad_uses_small_absolute_or_relative_tolerance() -> None:
    references = (60, 60, 60, 60, 60)

    accepted = assess_segment_sample(
        duration_seconds=65,
        distance_m=500,
        confidence="high",
        accepted_reference_durations=references,
    )
    rejected = assess_segment_sample(
        duration_seconds=67,
        distance_m=500,
        confidence="high",
        accepted_reference_durations=references,
    )

    assert accepted.accepted is True
    assert rejected.rejection_reason == "mad_outlier"
