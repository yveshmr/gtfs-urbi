from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Literal

from app.services.segment_crossing import CrossingConfidence

RejectionReason = Literal["speed_over_80", "mad_outlier", "invalid_measurement"]

MAX_AVERAGE_SPEED_KMH = 80.0
MIN_MAD_REFERENCE_COUNT = 5
MODIFIED_Z_SCORE_LIMIT = 3.5
HIGH_CONFIDENCE_WEIGHT = 1.0
REDUCED_CONFIDENCE_WEIGHT = 0.5
_MAD_ZERO_MINIMUM_TOLERANCE_SECONDS = 5.0
_MAD_ZERO_RELATIVE_TOLERANCE = 0.10


@dataclass(frozen=True, slots=True)
class SegmentSampleAssessment:
    accepted: bool
    weight: float
    rejection_reason: RejectionReason | None
    reference_count: int
    reference_median_seconds: float | None
    reference_mad_seconds: float | None
    modified_z_score: float | None


def assess_segment_sample(
    *,
    duration_seconds: float,
    distance_m: float,
    confidence: CrossingConfidence,
    accepted_reference_durations: tuple[float, ...],
) -> SegmentSampleAssessment:
    references = tuple(
        value for value in accepted_reference_durations if math.isfinite(value) and value > 0
    )
    reference_count = len(references)

    if (
        not math.isfinite(duration_seconds)
        or not math.isfinite(distance_m)
        or duration_seconds <= 0
        or distance_m <= 0
    ):
        return _rejected("invalid_measurement", reference_count)

    speed_kmh = distance_m / duration_seconds * 3.6
    if speed_kmh > MAX_AVERAGE_SPEED_KMH:
        return _rejected("speed_over_80", reference_count)

    if reference_count < MIN_MAD_REFERENCE_COUNT:
        return SegmentSampleAssessment(
            accepted=True,
            weight=REDUCED_CONFIDENCE_WEIGHT,
            rejection_reason=None,
            reference_count=reference_count,
            reference_median_seconds=None,
            reference_mad_seconds=None,
            modified_z_score=None,
        )

    median = statistics.median(references)
    mad = statistics.median(abs(value - median) for value in references)
    deviation = abs(duration_seconds - median)
    modified_z_score: float | None
    if mad == 0:
        tolerance = max(
            _MAD_ZERO_MINIMUM_TOLERANCE_SECONDS,
            median * _MAD_ZERO_RELATIVE_TOLERANCE,
        )
        modified_z_score = None
        is_outlier = deviation > tolerance
    else:
        modified_z_score = 0.6745 * deviation / mad
        is_outlier = modified_z_score > MODIFIED_Z_SCORE_LIMIT

    if is_outlier:
        return SegmentSampleAssessment(
            accepted=False,
            weight=0.0,
            rejection_reason="mad_outlier",
            reference_count=reference_count,
            reference_median_seconds=median,
            reference_mad_seconds=mad,
            modified_z_score=modified_z_score,
        )

    return SegmentSampleAssessment(
        accepted=True,
        weight=(HIGH_CONFIDENCE_WEIGHT if confidence == "high" else REDUCED_CONFIDENCE_WEIGHT),
        rejection_reason=None,
        reference_count=reference_count,
        reference_median_seconds=median,
        reference_mad_seconds=mad,
        modified_z_score=modified_z_score,
    )


def _rejected(
    reason: RejectionReason,
    reference_count: int,
) -> SegmentSampleAssessment:
    return SegmentSampleAssessment(
        accepted=False,
        weight=0.0,
        rejection_reason=reason,
        reference_count=reference_count,
        reference_median_seconds=None,
        reference_mad_seconds=None,
        modified_z_score=None,
    )
