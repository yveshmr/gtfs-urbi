from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prescription import VehicleSwapDecision, VehicleSwapDecisionEvent
from app.schemas.vehicle_swap import (
    SwapDecisionListResponse,
    SwapDecisionResponse,
)
from app.services.vehicle_swap_prescription import query_vehicle_swap_prescriptions


class ExchangeGroupNotCurrentError(RuntimeError):
    """Raised when an operator acts on a group from an obsolete snapshot."""


class ExchangeGroupDecisionConflictError(RuntimeError):
    """Raised when an operator requests an invalid state transition."""


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "in_analysis": {"claimed", "executed", "rejected"},
    "claimed": {"executed", "rejected"},
    "executed": set(),
    "rejected": set(),
}


def _response(decision: VehicleSwapDecision) -> SwapDecisionResponse:
    executed = decision.status == "executed"
    return SwapDecisionResponse(
        execution_key=decision.execution_key,
        group_id=decision.group_id,
        terminal_id=decision.terminal_id,
        snapshot_generated_at=decision.snapshot_generated_at,
        status=decision.status,
        updated_at=decision.updated_at,
        updated_by=decision.updated_by,
        rejection_reason=decision.rejection_reason,
        executed_at=decision.updated_at if executed else None,
        executed_by=decision.updated_by if executed else None,
    )


async def update_exchange_group_decision(
    session: AsyncSession,
    *,
    execution_key: str,
    decision_status: str,
    updated_by: str,
    updated_at: datetime,
    rejection_reason: str | None = None,
) -> SwapDecisionResponse:
    existing = await session.get(VehicleSwapDecision, execution_key)
    if existing is not None:
        if existing.status == decision_status:
            return _response(existing)
        if decision_status not in _ALLOWED_TRANSITIONS[existing.status]:
            raise ExchangeGroupDecisionConflictError(
                f"Cannot transition an exchange group from {existing.status} to {decision_status}."
            )

    prescription = await query_vehicle_swap_prescriptions(
        session,
        evaluated_at=updated_at,
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

    normalized_actor = updated_by.strip()
    normalized_reason = rejection_reason.strip() if rejection_reason else None
    event_time = updated_at.astimezone(UTC)
    if existing is None:
        decision = VehicleSwapDecision(
            execution_key=execution_key,
            group_id=group.group_id,
            terminal_id=group.terminal_id,
            snapshot_generated_at=prescription.snapshot_generated_at,
            status=decision_status,
            updated_at=event_time,
            updated_by=normalized_actor,
            rejection_reason=normalized_reason,
            group_snapshot=group.model_dump(mode="json"),
        )
        session.add(decision)
    else:
        decision = existing
        decision.status = decision_status
        decision.updated_at = event_time
        decision.updated_by = normalized_actor
        decision.rejection_reason = normalized_reason
        decision.group_snapshot = group.model_dump(mode="json")

    session.add(
        VehicleSwapDecisionEvent(
            id=uuid.uuid4(),
            execution_key=execution_key,
            status=decision_status,
            occurred_at=event_time,
            actor=normalized_actor,
            reason=normalized_reason,
        )
    )
    await session.commit()
    return _response(decision)


async def execute_exchange_group(
    session: AsyncSession,
    *,
    execution_key: str,
    executed_by: str,
    executed_at: datetime,
) -> SwapDecisionResponse:
    return await update_exchange_group_decision(
        session,
        execution_key=execution_key,
        decision_status="executed",
        updated_by=executed_by,
        updated_at=executed_at,
    )


async def query_recent_exchange_group_decisions(
    session: AsyncSession,
    *,
    evaluated_at: datetime,
) -> SwapDecisionListResponse:
    result = await session.scalars(
        select(VehicleSwapDecision)
        .where(
            VehicleSwapDecision.updated_at
            >= evaluated_at.astimezone(UTC) - timedelta(hours=24)
        )
        .order_by(VehicleSwapDecision.updated_at.desc())
        .limit(500)
    )
    decisions = [_response(item) for item in result]
    return SwapDecisionListResponse(count=len(decisions), decisions=decisions)
