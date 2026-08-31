from datetime import UTC, datetime, timedelta

from app.services.vehicle_swap_optimizer import (
    VehicleCommitment,
    build_exchange_groups,
    optimize_terminal_assignments,
)

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


def commitment(
    vehicle_prefix: str,
    *,
    arrival_minutes: int,
    departure_minutes: int,
) -> VehicleCommitment:
    return VehicleCommitment(
        vehicle_prefix=vehicle_prefix,
        terminal_id="terminal-1",
        arrival_at=NOW + timedelta(minutes=arrival_minutes),
        departure_at=NOW + timedelta(minutes=departure_minutes),
        current_trip_id=f"current-{vehicle_prefix}",
        current_route_id=f"route-{vehicle_prefix}",
        next_line=f"line-{vehicle_prefix}",
        next_direction="0",
        next_destination=f"destination-{vehicle_prefix}",
        next_schedule_position=f"position-{vehicle_prefix}",
        eta_reliability=0.9,
        eta_source_counts={"live": 2},
    )


def test_optimizer_reduces_total_delay_with_pair_swap() -> None:
    plan = optimize_terminal_assignments(
        [
            commitment("A", arrival_minutes=20, departure_minutes=0),
            commitment("B", arrival_minutes=-5, departure_minutes=30),
        ],
        evaluated_at=NOW - timedelta(minutes=20),
    )

    assert plan is not None
    assert plan.baseline_total_delay_seconds == 20 * 60
    assert plan.proposed_total_delay_seconds == 0
    assert {
        item.commitment.vehicle_prefix: item.assigned_vehicle.vehicle_prefix
        for item in plan.assignments
    } == {"A": "B", "B": "A"}


def test_optimizer_supports_terminal_wide_reallocation_chain() -> None:
    plan = optimize_terminal_assignments(
        [
            commitment("A", arrival_minutes=35, departure_minutes=0),
            commitment("B", arrival_minutes=-5, departure_minutes=20),
            commitment("C", arrival_minutes=15, departure_minutes=40),
        ],
        evaluated_at=NOW - timedelta(minutes=30),
    )

    assert plan is not None
    assert plan.saved_delay_seconds == 35 * 60
    assert {
        item.commitment.vehicle_prefix: item.assigned_vehicle.vehicle_prefix
        for item in plan.assignments
    } == {"A": "B", "B": "C", "C": "A"}
    groups = build_exchange_groups(plan)
    assert len(groups) == 1
    assert groups[0].group_id == "terminal-1-G01"
    assert groups[0].vehicle_prefixes == ("A", "B", "C")
    assert groups[0].saved_delay_seconds == 35 * 60


def test_viable_commitment_inside_window_is_protected() -> None:
    plan = optimize_terminal_assignments(
        [
            commitment("A", arrival_minutes=20, departure_minutes=0),
            commitment("B", arrival_minutes=-5, departure_minutes=2),
        ],
        evaluated_at=NOW - timedelta(minutes=5),
    )

    assert plan is None


def test_delay_must_be_strictly_greater_than_ten_minutes() -> None:
    plan = optimize_terminal_assignments(
        [
            commitment("A", arrival_minutes=10, departure_minutes=0),
            commitment("B", arrival_minutes=-5, departure_minutes=30),
        ],
        evaluated_at=NOW - timedelta(minutes=20),
    )

    assert plan is None
