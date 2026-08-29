from fastapi import APIRouter

from app.api.v1.segments import router as segments_router
from app.api.v1.vehicles import router as vehicles_router

router = APIRouter()
router.include_router(segments_router)
router.include_router(vehicles_router)
