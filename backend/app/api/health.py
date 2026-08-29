from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import check_database_connection, get_database_session
from app.schemas.health import (
    HealthResponse,
    OperationalHealthResponse,
    ReadinessResponse,
)
from app.services.operational_health import query_cittati_operational_status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "Banco de dados indisponível"}},
)
async def readiness() -> ReadinessResponse:
    try:
        await check_database_connection()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "database": "unavailable",
            },
        ) from error

    return ReadinessResponse(
        status="ready",
        database="ok",
    )


@router.get(
    "/health/operational",
    response_model=OperationalHealthResponse,
    responses={503: {"description": "Ingestão Cittati ausente ou defasada"}},
)
async def operational_health(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> OperationalHealthResponse:
    settings = get_settings()
    operational_status = await query_cittati_operational_status(
        session,
        now=datetime.now(UTC),
        stale_after_seconds=settings.cittati_operational_stale_after_seconds,
    )
    response = OperationalHealthResponse(
        source="cittati",
        **asdict(operational_status),
    )
    if operational_status.status != "operational":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(mode="json"),
        )
    return response
