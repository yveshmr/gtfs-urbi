from fastapi import APIRouter
from app.core.state import rt
from app.services.gtfs_rt import fetch_vehicle_positions

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

@router.get("/debug/stop_times/count")
def count_stop_times():
    return {"trips_with_stop_times": len(rt.stop_times)}

@router.get("/debug/segments/count")
def count_segments():
    return {"segments": len(rt.segments)}

@router.get("/debug/segments/sample")
def sample_segment():
    for seg in rt.segments.values():
        return seg

@router.get("/debug/vehicles/count")
def count_vehicles():
    feed = fetch_vehicle_positions()
    return {"vehicles": len(feed.entity)}
