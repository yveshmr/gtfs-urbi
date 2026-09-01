from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.vehicle_swap import (
    ExecuteExchangeGroupRequest,
    SwapExecutionListResponse,
    SwapExecutionResponse,
    VehicleSwapPrescriptionResponse,
)
from app.services.vehicle_swap_execution import (
    ExchangeGroupNotCurrentError,
    execute_exchange_group,
    query_recent_exchange_group_executions,
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


@router.get("/vehicle-swap-executions", response_model=SwapExecutionListResponse)
async def vehicle_swap_executions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapExecutionListResponse:
    return await query_recent_exchange_group_executions(
        session,
        evaluated_at=datetime.now(UTC),
    )


@router.post(
    "/vehicle-swap-executions",
    response_model=SwapExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_vehicle_swap_execution(
    request: ExecuteExchangeGroupRequest,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SwapExecutionResponse:
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
