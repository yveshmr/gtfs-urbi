from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.vehicle_swap import (
    ExecuteExchangeGroupRequest,
    SwapDecisionListResponse,
    SwapDecisionResponse,
    UpdateExchangeGroupDecisionRequest,
    VehicleSwapPrescriptionResponse,
)
from app.services.vehicle_swap_execution import (
    ExchangeGroupDecisionConflictError,
    ExchangeGroupNotCurrentError,
    execute_exchange_group,
    query_recent_exchange_group_decisions,
    update_exchange_group_decision,
)
from app.services.vehicle_swap_prescription import query_vehicle_swap_prescriptions

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.get("/vehicle-swaps", response_model=VehicleSwapPrescriptionResponse)
async def vehicle_swap_prescriptions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> VehicleSwapPrescriptionResponse:
    return await query_vehicle_swap_prescriptions(
        session,
        evaluated_at=datetime.now(UTC),
    )


@router.get("/vehicle-swap-decisions", response_model=SwapDecisionListResponse)
async def vehicle_swap_decisions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapDecisionListResponse:
    return await query_recent_exchange_group_decisions(
        session,
        evaluated_at=datetime.now(UTC),
    )


@router.post(
    "/vehicle-swap-decisions",
    response_model=SwapDecisionResponse,
)
async def update_vehicle_swap_decision(
    request: UpdateExchangeGroupDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapDecisionResponse:
    try:
        return await update_exchange_group_decision(
            session,
            execution_key=request.execution_key,
            decision_status=request.status,
            updated_by=request.updated_by,
            updated_at=datetime.now(UTC),
            rejection_reason=request.rejection_reason,
        )
    except ExchangeGroupNotCurrentError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O grupo mudou desde a última atualização. Revise a prescrição atual.",
        ) from error
    except ExchangeGroupDecisionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este grupo já possui uma decisão final e não pode ser alterado.",
        ) from error


@router.get("/vehicle-swap-executions", response_model=SwapDecisionListResponse)
async def vehicle_swap_executions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapDecisionListResponse:
    return await query_recent_exchange_group_decisions(
        session,
        evaluated_at=datetime.now(UTC),
    )


@router.post(
    "/vehicle-swap-executions",
    response_model=SwapDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_vehicle_swap_execution(
    request: ExecuteExchangeGroupRequest,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapDecisionResponse:
    try:
        return await execute_exchange_group(
            session,
            execution_key=request.execution_key,
            executed_by=request.executed_by,
            executed_at=datetime.now(UTC),
        )
    except ExchangeGroupNotCurrentError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O grupo mudou desde a última atualização. Revise a prescrição atual.",
        ) from error
    except ExchangeGroupDecisionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este grupo já possui uma decisão final e não pode ser alterado.",
        ) from error
