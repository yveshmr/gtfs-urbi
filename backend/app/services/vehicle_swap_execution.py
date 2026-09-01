from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prescription import VehicleSwapExecution
from app.schemas.vehicle_swap import (
    SwapExecutionListResponse,
    SwapExecutionResponse,
)
from app.services.vehicle_swap_prescription import query_vehicle_swap_prescriptions


class ExchangeGroupNotCurrentError(RuntimeError):
    """Raised when an operator tries to execute a group from an obsolete snapshot."""


def _response(execution: VehicleSwapExecution) -> SwapExecutionResponse:
    return SwapExecutionResponse(
        execution_key=execution.execution_key,
        group_id=execution.group_id,
        terminal_id=execution.terminal_id,
        snapshot_generated_at=execution.snapshot_generated_at,
        executed_at=execution.executed_at,
        executed_by=execution.executed_by,
    )


async def execute_exchange_group(
    session: AsyncSession,
    *,
    execution_key: str,
    executed_by: str,
    executed_at: datetime,
) -> SwapExecutionResponse:
    existing = await session.get(VehicleSwapExecution, execution_key)
    if existing is not None:
        return _response(existing)

    prescription = await query_vehicle_swap_prescriptions(
        session,
        evaluated_at=executed_at,
    )
    group = next(
        (
            group
            for plan in prescription.plans
            for group in plan.exchange_groups
            if group.execution_key == execution_key
        ),
        None,
    )
    if group is None or prescription.snapshot_generated_at is None:
        raise ExchangeGroupNotCurrentError(
            "The exchange group is no longer present in the current prescription."
        )

    execution = VehicleSwapExecution(
        execution_key=execution_key,
        group_id=group.group_id,
        terminal_id=group.terminal_id,
        snapshot_generated_at=prescription.snapshot_generated_at,
        executed_at=executed_at.astimezone(UTC),
        executed_by=executed_by.strip(),
        group_snapshot=group.model_dump(mode="json"),
    )
    session.add(execution)
    await session.commit()
    return _response(execution)


async def query_recent_exchange_group_executions(
    session: AsyncSession,
    *,
    evaluated_at: datetime,
) -> SwapExecutionListResponse:
    result = await session.scalars(
        select(VehicleSwapExecution)
        .where(
            VehicleSwapExecution.executed_at
            >= evaluated_at.astimezone(UTC) - timedelta(hours=24)
        )
        .order_by(VehicleSwapExecution.executed_at.desc())
        .limit(500)
    )
    executions = [_response(item) for item in result]
    return SwapExecutionListResponse(count=len(executions), executions=executions)
