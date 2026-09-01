from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.services.vehicle_swap_execution as execution_module
import pytest
from app.services.vehicle_swap_execution import (
    ExchangeGroupNotCurrentError,
    execute_exchange_group,
)

NOW = datetime(2026, 8, 31, 15, tzinfo=UTC)


class FakeSession:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.added: object | None = None
        self.commits = 0

    async def get(self, model: object, key: str) -> object | None:
        return self.existing

    def add(self, value: object) -> None:
        self.added = value

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_records_current_exchange_group(monkeypatch) -> None:
    group = SimpleNamespace(
        execution_key="a" * 64,
        group_id="terminal-G01",
        terminal_id="terminal",
        model_dump=lambda **_: {"execution_key": "a" * 64},
    )
    monkeypatch.setattr(
        execution_module,
        "query_vehicle_swap_prescriptions",
        AsyncMock(
            return_value=SimpleNamespace(
                plans=[SimpleNamespace(exchange_groups=[group])],
                snapshot_generated_at=NOW,
            )
        ),
    )
    session = FakeSession()

    response = await execute_exchange_group(
        session,  # type: ignore[arg-type]
        execution_key="a" * 64,
        executed_by=" Operador 1 ",
        executed_at=NOW,
    )

    assert response.executed_by == "Operador 1"
    assert response.group_id == "terminal-G01"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_rejects_group_that_is_no_longer_current(monkeypatch) -> None:
    monkeypatch.setattr(
        execution_module,
        "query_vehicle_swap_prescriptions",
        AsyncMock(
            return_value=SimpleNamespace(plans=[], snapshot_generated_at=NOW)
        ),
    )

    with pytest.raises(ExchangeGroupNotCurrentError):
        await execute_exchange_group(
            FakeSession(),  # type: ignore[arg-type]
            execution_key="a" * 64,
            executed_by="Operador 1",
            executed_at=NOW,
        )
