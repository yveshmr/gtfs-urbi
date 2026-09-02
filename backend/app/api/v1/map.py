from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.map import (
    ProjectedVehiclePositionListResponse,
    SegmentSpeedMapResponse,
    TripGeometryResponse,
)
from app.services.map_query import (
    TripGeometryNotFoundError,
    query_projected_vehicle_positions,
    query_trip_geometry,
)
from app.services.segment_map_query import query_segment_speed_map

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/vehicles", response_model=ProjectedVehiclePositionListResponse)
async def projected_vehicle_positions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    response: Response,
) -> ProjectedVehiclePositionListResponse:
    response.headers["Cache-Control"] = "no-store"
    return await query_projected_vehicle_positions(
        session,
        generated_at=datetime.now(UTC),
    )


@router.get("/segments", response_model=SegmentSpeedMapResponse)
async def segment_speeds(
    session: Annotated[AsyncSession, Depends(get_database_session)],
    response: Response,
) -> SegmentSpeedMapResponse:
    response.headers["Cache-Control"] = "no-store"
    return await query_segment_speed_map(session, generated_at=datetime.now(UTC))


@router.get("/trips/{trip_id}/geometry", response_model=TripGeometryResponse)
async def trip_geometry(
    trip_id: Annotated[str, Path(min_length=1, max_length=150)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    response: Response,
) -> TripGeometryResponse:
    response.headers["Cache-Control"] = "public, max-age=300"
    try:
        return await query_trip_geometry(session, trip_id=trip_id)
    except TripGeometryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip geometry not found.",
        ) from error
