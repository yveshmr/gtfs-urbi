from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from httpx import HTTPError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.integrations.cittati import CittatiError
from app.schemas.vehicle_eta import (
    VehicleEtaResponse,
    VehicleEtaSnapshotListResponse,
    build_vehicle_eta_response,
)
from app.schemas.vehicle_schedule import VehicleScheduleContextListResponse
from app.services.vehicle_eta_query import (
    VehicleEtaUnavailableError,
    VehicleNotFoundError,
    query_vehicle_eta,
)
from app.services.vehicle_eta_snapshot import query_vehicle_eta_snapshots
from app.services.vehicle_schedule_context import get_vehicle_schedule_context_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/schedule-contexts", response_model=VehicleScheduleContextListResponse)
async def vehicle_schedule_contexts() -> VehicleScheduleContextListResponse:
    try:
        service = get_vehicle_schedule_context_service()
        return await service.get(evaluated_at=datetime.now(UTC))
    except (CittatiError, HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cittati trip schedule is temporarily unavailable.",
        ) from error


@router.get("/eta-snapshots", response_model=VehicleEtaSnapshotListResponse)
async def vehicle_eta_snapshots(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> VehicleEtaSnapshotListResponse:
    return await query_vehicle_eta_snapshots(session)


@router.get("/{vehicle_prefix}/eta", response_model=VehicleEtaResponse)
async def vehicle_eta(
    vehicle_prefix: Annotated[str, Path(min_length=1, max_length=50)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    queried_at: datetime | None = None,
) -> VehicleEtaResponse:
    timestamp = queried_at or datetime.now(UTC)
    try:
        result = await query_vehicle_eta(
            session,
            vehicle_prefix=vehicle_prefix,
            queried_at=timestamp,
        )
    except VehicleNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found.",
        ) from error
    except VehicleEtaUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return build_vehicle_eta_response(result, queried_at=timestamp)
