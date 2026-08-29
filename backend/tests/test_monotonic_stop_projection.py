from app.services.monotonic_stop_projection import (
    StopProjectionCandidate,
    select_monotonic_stop_path,
)


def candidate(progress_m: float, distance_m: float = 0) -> StopProjectionCandidate:
    return StopProjectionCandidate(
        segment_sequence=int(progress_m),
        progress_m=progress_m,
        shape_position=progress_m / 1_000,
        distance_to_shape_m=distance_m,
    )


def test_selects_globally_best_monotonic_path_instead_of_greedy_dead_end() -> None:
    path = select_monotonic_stop_path(
        (
            (candidate(0), candidate(800)),
            (candidate(100, 10), candidate(900)),
            (candidate(200),),
        )
    )

    assert path is not None
    assert [item.progress_m for item in path] == [0, 100, 200]


def test_resolves_same_origin_and_destination_on_circular_shape() -> None:
    path = select_monotonic_stop_path(
        (
            (candidate(0), candidate(1_000)),
            (candidate(500),),
            (candidate(0), candidate(1_000)),
        )
    )

    assert path is not None
    assert [item.progress_m for item in path] == [0, 500, 1_000]


def test_returns_none_when_no_complete_monotonic_path_exists() -> None:
    path = select_monotonic_stop_path(
        (
            (candidate(500),),
            (candidate(100),),
        )
    )

    assert path is None
