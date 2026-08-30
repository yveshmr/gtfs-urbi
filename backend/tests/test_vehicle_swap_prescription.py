from datetime import UTC, datetime, timedelta

import pytest
from app.services.vehicle_swap_prescription import (
    query_vehicle_swap_prescriptions,
    resolve_planned_departure,
)

NOW = datetime(2026, 8, 30, 3, 55, tzinfo=UTC)  # 00:55 in Sao Paulo


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self.rows


class FakeSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def execute(self, statement: object) -> FakeResult:
        return FakeResult(self.rows)


def row(
    vehicle_prefix: str,
    *,
    arrival_at: datetime,
    next_planned_time: str,
) -> dict[str, object]:
    return {
        "generated_at": NOW,
        "vehicle_prefix": vehicle_prefix,
        "current_trip_id": f"trip-{vehicle_prefix}",
        "current_route_id": f"route-{vehicle_prefix}",
        "terminal_id": "terminal-1",
        "next_planned_time": next_planned_time,
        "next_schedule_position": f"position-{vehicle_prefix}",
        "next_line": f"line-{vehicle_prefix}",
        "next_direction": "0",
        "next_destination": f"destination-{vehicle_prefix}",
        "payload": {
            "future_time": {
                "service": {
                    "trip_end": {
                        "complete": True,
                        "estimated_at": arrival_at.isoformat(),
                        "reliability": 0.9,
                        "source_counts": {"live": 2},
                    }
                }
            }
        },
    }


def test_planned_departure_rolls_across_midnight() -> None:
    reference = datetime(2026, 8, 30, 2, 55, tzinfo=UTC)  # 23:55 in Sao Paulo

    result = resolve_planned_departure("00:10", reference=reference)

    assert result == datetime(2026, 8, 30, 3, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_query_builds_global_terminal_plan() -> None:
    response = await query_vehicle_swap_prescriptions(
        FakeSession(  # type: ignore[arg-type]
            [
                row(
                    "A",
                    arrival_at=NOW + timedelta(minutes=35),
                    next_planned_time="00:55",
                ),
                row(
                    "B",
                    arrival_at=NOW - timedelta(minutes=5),
                    next_planned_time="01:15",
                ),
                row(
                    "C",
                    arrival_at=NOW + timedelta(minutes=15),
                    next_planned_time="01:35",
                ),
            ]
        ),
        evaluated_at=NOW,
    )

    assert response.status == "ready"
    assert response.eligible_vehicle_count == 3
    assert response.plan_count == 1
    assert response.total_saved_delay_seconds == 35 * 60
    assert {
        assignment.commitment_vehicle_prefix: assignment.assigned_vehicle_prefix
        for assignment in response.plans[0].assignments
    } == {"A": "B", "B": "C", "C": "A"}


@pytest.mark.asyncio
async def test_query_rejects_stale_snapshot() -> None:
    stale_row = row("A", arrival_at=NOW, next_planned_time="00:55")
    stale_row["generated_at"] = NOW - timedelta(minutes=11)

    response = await query_vehicle_swap_prescriptions(
        FakeSession([stale_row]),  # type: ignore[arg-type]
        evaluated_at=NOW,
    )

    assert response.status == "stale"
    assert response.plans == []
