from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class VehicleCommitment:
    vehicle_prefix: str
    terminal_id: str
    arrival_at: datetime
    departure_at: datetime
    current_trip_id: str
    current_route_id: str
    next_line: str | None
    next_direction: str | None
    next_destination: str | None
    next_schedule_position: str | None
    eta_reliability: float
    eta_source_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class VehicleAssignment:
    commitment: VehicleCommitment
    assigned_vehicle: VehicleCommitment
    baseline_delay_seconds: int
    proposed_delay_seconds: int
    protected: bool

    @property
    def changed(self) -> bool:
        return self.commitment.vehicle_prefix != self.assigned_vehicle.vehicle_prefix

    @property
    def assigned_arrival_margin_seconds(self) -> int:
        return round(
            (self.commitment.departure_at - self.assigned_vehicle.arrival_at).total_seconds()
        )


@dataclass(frozen=True, slots=True)
class TerminalSwapPlan:
    terminal_id: str
    baseline_total_delay_seconds: int
    proposed_total_delay_seconds: int
    baseline_delayed_trip_count: int
    proposed_delayed_trip_count: int
    baseline_max_delay_seconds: int
    proposed_max_delay_seconds: int
    assignments: tuple[VehicleAssignment, ...]

    @property
    def saved_delay_seconds(self) -> int:
        return self.baseline_total_delay_seconds - self.proposed_total_delay_seconds


@dataclass(frozen=True, slots=True)
class ExchangeGroup:
    group_id: str
    terminal_id: str
    assignments: tuple[VehicleAssignment, ...]

    @property
    def execution_key(self) -> str:
        actions = "|".join(
            f"{item.commitment.vehicle_prefix}>{item.assigned_vehicle.vehicle_prefix}"
            f"@{item.commitment.departure_at.isoformat()}"
            for item in self.assignments
        )
        return hashlib.sha256(f"{self.terminal_id}|{actions}".encode()).hexdigest()

    @property
    def vehicle_prefixes(self) -> tuple[str, ...]:
        return tuple(item.commitment.vehicle_prefix for item in self.assignments)

    @property
    def baseline_total_delay_seconds(self) -> int:
        return sum(item.baseline_delay_seconds for item in self.assignments)

    @property
    def proposed_total_delay_seconds(self) -> int:
        return sum(item.proposed_delay_seconds for item in self.assignments)

    @property
    def saved_delay_seconds(self) -> int:
        return self.baseline_total_delay_seconds - self.proposed_total_delay_seconds

    @property
    def baseline_max_delay_seconds(self) -> int:
        return max((item.baseline_delay_seconds for item in self.assignments), default=0)

    @property
    def proposed_max_delay_seconds(self) -> int:
        return max((item.proposed_delay_seconds for item in self.assignments), default=0)

    @property
    def minimum_eta_reliability(self) -> float:
        return min(
            (item.assigned_vehicle.eta_reliability for item in self.assignments),
            default=0,
        )


def build_exchange_groups(plan: TerminalSwapPlan) -> tuple[ExchangeGroup, ...]:
    """Decompose the changed assignment permutation into closed exchange cycles."""
    changed_by_commitment = {
        item.commitment.vehicle_prefix: item for item in plan.assignments if item.changed
    }
    unvisited = set(changed_by_commitment)
    cycles: list[tuple[VehicleAssignment, ...]] = []
    while unvisited:
        start = min(unvisited)
        current = start
        cycle: list[VehicleAssignment] = []
        while current in unvisited:
            unvisited.remove(current)
            assignment = changed_by_commitment[current]
            cycle.append(assignment)
            current = assignment.assigned_vehicle.vehicle_prefix
        if current != start:
            raise ValueError("Changed vehicle assignments must form closed exchange cycles.")
        cycles.append(tuple(cycle))

    return tuple(
        ExchangeGroup(
            group_id=f"{plan.terminal_id}-G{index:02d}",
            terminal_id=plan.terminal_id,
            assignments=cycle,
        )
        for index, cycle in enumerate(cycles, start=1)
    )


def delay_seconds(arrival_at: datetime, departure_at: datetime) -> int:
    return max(0, round((arrival_at - departure_at).total_seconds()))


def _hungarian(costs: list[list[int]]) -> list[int]:
    """Return the selected column for each row of a square integer cost matrix."""
    size = len(costs)
    if size == 0:
        return []
    if any(len(row) != size for row in costs):
        raise ValueError("The assignment cost matrix must be square.")

    row_potential = [0] * (size + 1)
    column_potential = [0] * (size + 1)
    matched_row = [0] * (size + 1)
    previous_column = [0] * (size + 1)

    for row_index in range(1, size + 1):
        matched_row[0] = row_index
        current_column = 0
        minimum = [10**100] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[current_column] = True
            current_row = matched_row[current_column]
            delta = 10**100
            next_column = 0
            for column_index in range(1, size + 1):
                if used[column_index]:
                    continue
                reduced_cost = (
                    costs[current_row - 1][column_index - 1]
                    - row_potential[current_row]
                    - column_potential[column_index]
                )
                if reduced_cost < minimum[column_index]:
                    minimum[column_index] = reduced_cost
                    previous_column[column_index] = current_column
                if minimum[column_index] < delta:
                    delta = minimum[column_index]
                    next_column = column_index
            for column_index in range(size + 1):
                if used[column_index]:
                    row_potential[matched_row[column_index]] += delta
                    column_potential[column_index] -= delta
                else:
                    minimum[column_index] -= delta
            current_column = next_column
            if matched_row[current_column] == 0:
                break

        while True:
            prior = previous_column[current_column]
            matched_row[current_column] = matched_row[prior]
            current_column = prior
            if current_column == 0:
                break

    selected_column = [0] * size
    for column_index in range(1, size + 1):
        selected_column[matched_row[column_index] - 1] = column_index - 1
    return selected_column


def _assignment_cost(
    vehicle: VehicleCommitment,
    commitment: VehicleCommitment,
    *,
    group_size: int,
) -> int:
    delay = delay_seconds(vehicle.arrival_at, commitment.departure_at)
    idle = max(0, round((commitment.departure_at - vehicle.arrival_at).total_seconds()))
    idle = min(idle, 24 * 60 * 60)

    max_idle_total = group_size * 24 * 60 * 60
    swap_weight = max_idle_total + 1
    delayed_trip_weight = group_size * swap_weight + max_idle_total + 1
    delay_weight = group_size * delayed_trip_weight + group_size * swap_weight + max_idle_total + 1
    changed = vehicle.vehicle_prefix != commitment.vehicle_prefix
    return (
        delay * delay_weight
        + int(delay > 0) * delayed_trip_weight
        + int(changed) * swap_weight
        + idle
    )


def optimize_terminal_assignments(
    commitments: list[VehicleCommitment],
    *,
    evaluated_at: datetime,
    delay_threshold: timedelta = timedelta(minutes=10),
    protected_window: timedelta = timedelta(minutes=10),
) -> TerminalSwapPlan | None:
    if not commitments:
        return None
    terminal_ids = {item.terminal_id for item in commitments}
    if len(terminal_ids) != 1:
        raise ValueError("All commitments must belong to the same terminal.")

    commitments = sorted(commitments, key=lambda item: item.vehicle_prefix)
    baseline_delays = {
        item.vehicle_prefix: delay_seconds(item.arrival_at, item.departure_at)
        for item in commitments
    }
    threshold_seconds = round(delay_threshold.total_seconds())
    if not any(delay > threshold_seconds for delay in baseline_delays.values()):
        return None

    protected: list[VehicleCommitment] = []
    available: list[VehicleCommitment] = []
    for item in commitments:
        time_until_departure = item.departure_at - evaluated_at
        is_protected = (
            timedelta(0) <= time_until_departure <= protected_window
            and baseline_delays[item.vehicle_prefix] == 0
        )
        (protected if is_protected else available).append(item)

    selected = _hungarian(
        [
            [
                _assignment_cost(vehicle, commitment, group_size=len(available))
                for commitment in available
            ]
            for vehicle in available
        ]
    )
    assigned_by_commitment = {
        available[column_index].vehicle_prefix: available[row_index]
        for row_index, column_index in enumerate(selected)
    }

    assignments: list[VehicleAssignment] = []
    for commitment in commitments:
        is_protected = commitment in protected
        assigned_vehicle = (
            commitment if is_protected else assigned_by_commitment[commitment.vehicle_prefix]
        )
        assignments.append(
            VehicleAssignment(
                commitment=commitment,
                assigned_vehicle=assigned_vehicle,
                baseline_delay_seconds=baseline_delays[commitment.vehicle_prefix],
                proposed_delay_seconds=delay_seconds(
                    assigned_vehicle.arrival_at,
                    commitment.departure_at,
                ),
                protected=is_protected,
            )
        )

    baseline_values = [item.baseline_delay_seconds for item in assignments]
    proposed_values = [item.proposed_delay_seconds for item in assignments]
    plan = TerminalSwapPlan(
        terminal_id=commitments[0].terminal_id,
        baseline_total_delay_seconds=sum(baseline_values),
        proposed_total_delay_seconds=sum(proposed_values),
        baseline_delayed_trip_count=sum(value > 0 for value in baseline_values),
        proposed_delayed_trip_count=sum(value > 0 for value in proposed_values),
        baseline_max_delay_seconds=max(baseline_values, default=0),
        proposed_max_delay_seconds=max(proposed_values, default=0),
        assignments=tuple(assignments),
    )
    improved_target = any(
        assignment.baseline_delay_seconds > threshold_seconds
        and assignment.proposed_delay_seconds < assignment.baseline_delay_seconds
        and assignment.changed
        for assignment in assignments
    )
    if plan.saved_delay_seconds <= 0 or not improved_target:
        return None
    return plan
