from datetime import UTC, datetime

import pytest
from app.services.vehicle_eta_snapshot import refresh_vehicle_eta_snapshots

NOW = datetime(2026, 8, 29, 13, 2, tzinfo=UTC)


class FakeSession:
    def __init__(self, latest_generated_at: datetime | None) -> None:
        self.latest_generated_at = latest_generated_at
        self.execute_called = False

    async def scalar(self, statement: object) -> datetime | None:
        return self.latest_generated_at

    async def execute(self, statement: object, parameters: object) -> None:
        self.execute_called = True


@pytest.mark.asyncio
async def test_snapshot_refresh_runs_at_most_once_per_five_minute_window() -> None:
    session = FakeSession(NOW)

    result = await refresh_vehicle_eta_snapshots(  # type: ignore[arg-type]
        session,
        queried_at=NOW,
    )

    assert result.performed is False
    assert result.snapshot_count == 0
    assert session.execute_called is False
