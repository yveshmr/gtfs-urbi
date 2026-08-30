from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.vehicle_swap import VehicleSwapPrescriptionResponse
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
