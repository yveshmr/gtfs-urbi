from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.services.vehicle_swap_execution as execution_module
import pytest
from app.services.vehicle_swap_execution import (
    ExchangeGroupDecisionConflictError,
    ExchangeGroupNotCurrentError,
    execute_exchange_group,
    update_exchange_group_decision,
)

NOW = datetime(2026, 8, 31, 15, tzinfo=UTC)


class FakeSession:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.commits = 0

    async def get(self, model: object, key: str) -> object | None:
        return self.existing

    def add(self, value: object) -> None:
        self.added.append(value)

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
    assert response.status == "executed"
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


@pytest.mark.asyncio
async def test_records_rejection_reason_for_the_whole_group(monkeypatch) -> None:
    group = SimpleNamespace(
        execution_key="b" * 64,
        group_id="terminal-G02",
        terminal_id="terminal",
        model_dump=lambda **_: {"execution_key": "b" * 64, "vehicle_count": 3},
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

    response = await update_exchange_group_decision(
        session,  # type: ignore[arg-type]
        execution_key="b" * 64,
        decision_status="rejected",
        updated_by="Operador 2",
        updated_at=NOW,
        rejection_reason="Veículo indisponível no pátio",
    )

    assert response.status == "rejected"
    assert response.rejection_reason == "Veículo indisponível no pátio"
    assert len(session.added) == 2


@pytest.mark.asyncio
async def test_prevents_changing_a_final_decision() -> None:
    existing = SimpleNamespace(
        execution_key="c" * 64,
        group_id="terminal-G03",
        terminal_id="terminal",
        snapshot_generated_at=NOW,
        status="executed",
        updated_at=NOW,
        updated_by="Operador 1",
        rejection_reason=None,
    )
    with pytest.raises(ExchangeGroupDecisionConflictError):
        await update_exchange_group_decision(
            FakeSession(existing),  # type: ignore[arg-type]
            execution_key="c" * 64,
            decision_status="rejected",
            updated_by="Operador 2",
            updated_at=NOW,
            rejection_reason="Mudança tardia",
        )
