from fastapi import APIRouter
from app.core.state import rt
from app.services.vehicles import update_vehicles

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

@router.get("/debug/vehicles/count")
def count_vehicles():
    update_vehicles()
    return {"vehicles": len(rt.vehicles)}

@router.get("/debug/vehicles/sample")
def sample_vehicle():
    update_vehicles()

    if not rt.vehicles:
        return {"error": "no vehicles loaded"}

    first_key = next(iter(rt.vehicles))
    return rt.vehicles[first_key]

@router.get("/debug/vehicles/all")
def get_all_vehicles():
    update_vehicles()

    return {
        "count": len(rt.vehicles),
        "vehicles": list(rt.vehicles.values()),
    }

@router.get("/vehicles/enriched")
def vehicles_enriched():
    update_vehicles()

    enriched = []

    for vid, v in rt.vehicles.items():
        route = rt.routes.get(v["route_id"], {})

        enriched.append({
            "vehicle_label": v["vehicle_label"],
            "lat": v["lat"],
            "lon": v["lon"],
            "speed_kmh": v["speed_kmh"],
            "route_id": v["route_id"],
            "route_short_name": route.get("route_short_name"),
            "route_long_name": route.get("route_long_name"),
            "event_ts": v["event_ts"],
        })

    return enriched
