from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API operacional para localização, ETA e análise prescritiva.",
)

app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")
