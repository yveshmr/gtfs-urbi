from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.vehicle_swap import (
    ExchangeGroupResponse,
    SwapAssignmentResponse,
    TerminalSwapPlanResponse,
    VehicleSwapPrescriptionResponse,
)
from app.services.vehicle_swap_optimizer import (
    TerminalSwapPlan,
    VehicleAssignment,
    VehicleCommitment,
    build_exchange_groups,
    optimize_terminal_assignments,
)

_OPERATIONAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_DELAY_THRESHOLD = timedelta(minutes=10)
_PROTECTED_WINDOW = timedelta(minutes=10)
_MAX_SNAPSHOT_AGE = timedelta(minutes=10)


def resolve_planned_departure(value: str, *, reference: datetime) -> datetime:
    if reference.tzinfo is None:
        raise ValueError("The departure reference must include a timezone.")
    try:
        parsed_time = time.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"Unsupported planned departure time: {value!r}") from error

    local_reference = reference.astimezone(_OPERATIONAL_TIMEZONE)
    candidates = [
        datetime.combine(
            local_reference.date() + timedelta(days=day_offset),
            parsed_time,
            tzinfo=_OPERATIONAL_TIMEZONE,
        )
        for day_offset in (-1, 0, 1)
    ]
    return min(candidates, key=lambda candidate: abs(candidate - local_reference)).astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _commitment_from_row(
    row: dict[str, Any],
    *,
    evaluated_at: datetime,
) -> VehicleCommitment | None:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return None
    trip_end = payload.get("future_time", {}).get("service", {}).get("trip_end", {})
    if not isinstance(trip_end, dict) or not trip_end.get("complete"):
        return None
    arrival_at = _parse_datetime(trip_end.get("estimated_at"))
    if arrival_at is None:
        return None
    try:
        departure_at = resolve_planned_departure(
            str(row["next_planned_time"]),
            reference=evaluated_at,
        )
    except (KeyError, ValueError):
        return None

    source_counts = trip_end.get("source_counts")
    return VehicleCommitment(
        vehicle_prefix=str(row["vehicle_prefix"]),
        terminal_id=str(row["terminal_id"]),
        arrival_at=arrival_at,
        departure_at=departure_at,
        current_trip_id=str(row["current_trip_id"]),
        current_route_id=str(row["current_route_id"]),
        next_line=row.get("next_line"),
        next_direction=row.get("next_direction"),
        next_destination=row.get("next_destination"),
        next_schedule_position=row.get("next_schedule_position"),
        eta_reliability=float(trip_end.get("reliability") or 0),
        eta_source_counts=(
            {str(key): int(count) for key, count in source_counts.items()}
            if isinstance(source_counts, dict)
            else {}
        ),
    )


def _response_assignment(assignment: VehicleAssignment) -> SwapAssignmentResponse:
    return SwapAssignmentResponse(
        commitment_vehicle_prefix=assignment.commitment.vehicle_prefix,
        assigned_vehicle_prefix=assignment.assigned_vehicle.vehicle_prefix,
        departure_at=assignment.commitment.departure_at,
        commitment_vehicle_arrival_at=assignment.commitment.arrival_at,
        assigned_vehicle_arrival_at=assignment.assigned_vehicle.arrival_at,
        assigned_arrival_margin_seconds=assignment.assigned_arrival_margin_seconds,
        next_line=assignment.commitment.next_line,
        next_direction=assignment.commitment.next_direction,
        next_destination=assignment.commitment.next_destination,
        next_schedule_position=assignment.commitment.next_schedule_position,
        baseline_delay_seconds=assignment.baseline_delay_seconds,
        proposed_delay_seconds=assignment.proposed_delay_seconds,
        delay_reduction_seconds=(
            assignment.baseline_delay_seconds - assignment.proposed_delay_seconds
        ),
        eta_reliability=assignment.assigned_vehicle.eta_reliability,
        eta_source_counts=assignment.assigned_vehicle.eta_source_counts,
        protected=assignment.protected,
        changed=assignment.changed,
    )


def _response_plan(plan: TerminalSwapPlan) -> TerminalSwapPlanResponse:
    groups = build_exchange_groups(plan)
    return TerminalSwapPlanResponse(
        terminal_id=plan.terminal_id,
        baseline_total_delay_seconds=plan.baseline_total_delay_seconds,
        proposed_total_delay_seconds=plan.proposed_total_delay_seconds,
        saved_delay_seconds=plan.saved_delay_seconds,
        baseline_delayed_trip_count=plan.baseline_delayed_trip_count,
        proposed_delayed_trip_count=plan.proposed_delayed_trip_count,
        baseline_max_delay_seconds=plan.baseline_max_delay_seconds,
        proposed_max_delay_seconds=plan.proposed_max_delay_seconds,
        exchange_groups=[
            ExchangeGroupResponse(
                group_id=group.group_id,
                terminal_id=group.terminal_id,
                vehicle_prefixes=list(group.vehicle_prefixes),
                vehicle_count=len(group.assignments),
                baseline_total_delay_seconds=group.baseline_total_delay_seconds,
                proposed_total_delay_seconds=group.proposed_total_delay_seconds,
                saved_delay_seconds=group.saved_delay_seconds,
                baseline_max_delay_seconds=group.baseline_max_delay_seconds,
                proposed_max_delay_seconds=group.proposed_max_delay_seconds,
                minimum_eta_reliability=group.minimum_eta_reliability,
                steps=[_response_assignment(item) for item in group.assignments],
            )
            for group in groups
        ],
        assignments=[_response_assignment(item) for item in plan.assignments],
    )


async def query_vehicle_swap_prescriptions(
    session: AsyncSession,
    *,
    evaluated_at: datetime,
) -> VehicleSwapPrescriptionResponse:
    if evaluated_at.tzinfo is None:
        raise ValueError("The prescription timestamp must include a timezone.")
    evaluated_at = evaluated_at.astimezone(UTC)
    result = await session.execute(
        text(
            """
            WITH latest_snapshot AS (
                SELECT MAX(generated_at) AS generated_at
                FROM realtime.vehicle_eta_snapshots
            )
            SELECT
                snapshot.generated_at,
                snapshot.vehicle_prefix,
                snapshot.trip_id AS current_trip_id,
                snapshot.route_id AS current_route_id,
                snapshot.payload,
                state.next_planned_time,
                state.next_trip_point AS terminal_id,
                state.next_schedule_position,
                state.next_line,
                state.next_direction,
                state.next_trip_destination AS next_destination
            FROM latest_snapshot
            JOIN realtime.vehicle_eta_snapshots AS snapshot
              ON snapshot.generated_at = latest_snapshot.generated_at
            JOIN realtime.vehicle_current_states AS state
              ON state.vehicle_prefix = snapshot.vehicle_prefix
             AND state.trip_id = snapshot.trip_id
            WHERE state.next_planned_time IS NOT NULL
              AND state.next_trip_point IS NOT NULL
            ORDER BY state.next_trip_point, snapshot.vehicle_prefix
            """
        )
    )
    rows = [dict(row) for row in result.mappings()]
    if not rows:
        return VehicleSwapPrescriptionResponse(
            status="no_data",
            evaluated_at=evaluated_at,
            snapshot_generated_at=None,
            snapshot_age_seconds=None,
            delay_threshold_minutes=10,
            protected_window_minutes=10,
            eligible_vehicle_count=0,
            terminal_count=0,
            plan_count=0,
            total_saved_delay_seconds=0,
            plans=[],
        )

    generated_at = rows[0]["generated_at"]
    snapshot_age = max(0.0, (evaluated_at - generated_at).total_seconds())
    if snapshot_age > _MAX_SNAPSHOT_AGE.total_seconds():
        return VehicleSwapPrescriptionResponse(
            status="stale",
            evaluated_at=evaluated_at,
            snapshot_generated_at=generated_at,
            snapshot_age_seconds=snapshot_age,
            delay_threshold_minutes=10,
            protected_window_minutes=10,
            eligible_vehicle_count=0,
            terminal_count=0,
            plan_count=0,
            total_saved_delay_seconds=0,
            plans=[],
        )

    commitments_by_terminal: dict[str, list[VehicleCommitment]] = defaultdict(list)
    for row in rows:
        commitment = _commitment_from_row(row, evaluated_at=evaluated_at)
        if commitment is not None:
            commitments_by_terminal[commitment.terminal_id].append(commitment)

    plans = [
        plan
        for terminal_id in sorted(commitments_by_terminal)
        if (
            plan := optimize_terminal_assignments(
                commitments_by_terminal[terminal_id],
                evaluated_at=evaluated_at,
                delay_threshold=_DELAY_THRESHOLD,
                protected_window=_PROTECTED_WINDOW,
            )
        )
        is not None
    ]
    response_plans = [_response_plan(plan) for plan in plans]
    return VehicleSwapPrescriptionResponse(
        status="ready",
        evaluated_at=evaluated_at,
        snapshot_generated_at=generated_at,
        snapshot_age_seconds=snapshot_age,
        delay_threshold_minutes=10,
        protected_window_minutes=10,
        eligible_vehicle_count=sum(len(items) for items in commitments_by_terminal.values()),
        terminal_count=len(commitments_by_terminal),
        plan_count=len(response_plans),
        total_saved_delay_seconds=sum(plan.saved_delay_seconds for plan in plans),
        plans=response_plans,
    )
