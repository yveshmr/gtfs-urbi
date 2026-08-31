from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.services.vehicle_schedule_context import get_vehicle_schedule_context_service

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    if get_vehicle_schedule_context_service.cache_info().currsize:
        await get_vehicle_schedule_context_service().aclose()
        get_vehicle_schedule_context_service.cache_clear()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API operacional para localização, ETA e análise prescritiva.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")
