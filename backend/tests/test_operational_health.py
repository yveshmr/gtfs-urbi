from datetime import UTC, datetime, timedelta

import pytest
from app.services.operational_health import query_cittati_operational_status

NOW = datetime(2026, 8, 29, 13, tzinfo=UTC)


class FakeResult:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    class Mappings:
        def __init__(self, row: dict[str, object]) -> None:
            self.row = row

        def one(self) -> dict[str, object]:
            return self.row

    def mappings(self) -> Mappings:
        return self.Mappings(self.row)


class FakeSession:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    async def execute(self, statement: object) -> FakeResult:
        return FakeResult(self.row)


@pytest.mark.asyncio
async def test_operational_health_reports_recent_success() -> None:
    result = await query_cittati_operational_status(  # type: ignore[arg-type]
        FakeSession(
            {
                "latest_attempt_status": "succeeded",
                "last_success_at": NOW - timedelta(seconds=12),
            }
        ),
        now=NOW,
        stale_after_seconds=60,
    )

    assert result.status == "operational"
    assert result.last_success_age_seconds == 12


@pytest.mark.asyncio
async def test_operational_health_reports_stale_ingestion() -> None:
    result = await query_cittati_operational_status(  # type: ignore[arg-type]
        FakeSession(
            {
                "latest_attempt_status": "succeeded",
                "last_success_at": NOW - timedelta(seconds=61),
            }
        ),
        now=NOW,
        stale_after_seconds=60,
    )

    assert result.status == "degraded"
