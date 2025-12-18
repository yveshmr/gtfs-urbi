from fastapi import APIRouter
from app.core.state import rt

router = APIRouter()

@router.get("/debug/stops/count")
def count_stops():
    return {"stops": len(rt.stops)}

@router.get("/debug/routes/count")
def count_routes():
    return {"routes": len(rt.routes)}

@router.get("/debug/trips/count")
def count_trips():
    return {"trips": len(rt.trips)}
