from fastapi import APIRouter
from app.core.state import rt

router = APIRouter()

@router.get("/debug/stops/count")
def count_stops():
    return {
        "stops_count": len(rt.stops)
    }
