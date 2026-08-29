from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.segment_estimate import (
    SegmentEstimateResponse,
    SegmentEstimateValue,
)
from app.services.segment_estimate_query import query_segment_estimates

router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("/estimate", response_model=SegmentEstimateResponse)
async def segment_estimate(
    origin_stop_id: Annotated[str, Query(min_length=1, max_length=100)],
    destination_stop_id: Annotated[str, Query(min_length=1, max_length=100)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    route_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    direction_id: Annotated[int | None, Query(ge=0, le=1)] = None,
    queried_at: datetime | None = None,
) -> SegmentEstimateResponse:
    timestamp = queried_at or datetime.now(UTC)
    try:
        estimates = await query_segment_estimates(
            session,
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            route_id=route_id,
            direction_id=direction_id,
            queried_at=timestamp,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return SegmentEstimateResponse(
        queried_at=timestamp,
        origin_stop_id=origin_stop_id,
        destination_stop_id=destination_stop_id,
        route_id=route_id,
        direction_id=direction_id,
        physical=SegmentEstimateValue(**asdict(estimates.physical)),
        service=(
            SegmentEstimateValue(**asdict(estimates.service))
            if estimates.service is not None
            else None
        ),
    )
