from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.vehicle_eta import (
    EtaProjectionResponse,
    EtaScenarioResponse,
    VehicleEtaResponse,
)
from app.services.vehicle_eta_query import (
    VehicleEtaUnavailableError,
    VehicleNotFoundError,
    query_vehicle_eta,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


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

    return VehicleEtaResponse(
        queried_at=timestamp,
        vehicle_prefix=result.vehicle_prefix,
        trip_id=result.trip_id,
        route_id=result.route_id,
        direction_id=result.direction_id,
        next_stop_id=result.next_stop_id,
        terminal_stop_id=result.terminal_stop_id,
        remaining_segment_count=result.remaining_segment_count,
        current_time=EtaScenarioResponse(
            physical=EtaProjectionResponse(**asdict(result.current_time_physical)),
            service=EtaProjectionResponse(**asdict(result.current_time_service)),
        ),
        future_time=EtaScenarioResponse(
            physical=EtaProjectionResponse(**asdict(result.future_time_physical)),
            service=EtaProjectionResponse(**asdict(result.future_time_service)),
        ),
    )
