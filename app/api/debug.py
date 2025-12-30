from fastapi import APIRouter
import random

from app.core.state import rt
from app.services.vehicles import update_vehicles
from app.services.vehicle_progress import compute_vehicle_progress
from app.services.trip_lookup import get_trips_for_route
from app.services.stop_times_lookup import get_stop_times_for_trip


router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/state")
def state_summary():
    return {
        "stops": len(rt.stops or {}),
        "routes": len(rt.routes or {}),
        "trips": len(rt.trips or {}),
        "stop_times": len(rt.stop_times or {}),
        "shapes": len(rt.shapes or {}),
        "vehicles": len(rt.vehicles or {}),
        "route_shapes": len(rt.route_shapes or {}),
    }


# ---------------- VEHICLES ---------------- #

@router.get("/sample/vehicle")
def sample_vehicle():
    update_vehicles()

    if not rt.vehicles:
        return {"vehicles": 0}

    vid = random.choice(list(rt.vehicles.keys()))
    return rt.vehicles[vid]


@router.get("/vehicles")
def list_all_vehicles():
    update_vehicles()
    return list(rt.vehicles.values())


@router.get("/vehicle/{vehicle_id}")
def get_vehicle(vehicle_id: str):
    update_vehicles()
    return rt.vehicles.get(vehicle_id)


@router.get("/vehicle_progress/{vehicle_id}")
def debug_vehicle_progress(vehicle_id: str):
    update_vehicles()

    v = rt.vehicles.get(vehicle_id)

    if not v:
        return {"ok": False, "reason": "vehicle not found", "vehicle_id": vehicle_id}

    return {
        "ok": True,
        "vehicle_id": vehicle_id,
        "progress": compute_vehicle_progress(v)
    }


# ---------------- SHAPES ---------------- #

@router.get("/shapes/sample")
def shapes_sample():
    if not rt.shapes:
        return {"ok": False, "reason": "no shapes loaded"}

    sid = random.choice(list(rt.shapes.keys()))
    pts = rt.shapes[sid]

    return {
        "ok": True,
        "shape_id": sid,
        "point_count": len(pts),
        "first_points": pts[:3],
    }


# ---------------- STOP TIMES ---------------- #

@router.get("/trip/stop_times/{trip_id}")
def debug_trip_stop_times(trip_id: str):
    stops = get_stop_times_for_trip(trip_id)

    if not stops:
        return {
            "trip_id": trip_id,
            "exists": False,
            "len": 0,
            "sample": None,
        }

    return {
        "trip_id": trip_id,
        "exists": True,
        "len": len(stops),
        "sample": stops[:5],
    }


# ---------------- ROUTE → SHAPES ---------------- #

@router.get("/route/{route_id}/shapes/{direction_id}")
def debug_route_shapes(route_id: str, direction_id: int):
    trips = get_trips_for_route(route_id, direction_id)

    if not trips:
        return {
            "ok": False,
            "reason": "no trips",
            "route_id": route_id,
            "direction_id": direction_id,
        }

    shapes = {t["trip_id"]: t["shape_id"] for t in trips if t.get("shape_id")}

    return {
        "ok": True,
        "route_id": route_id,
        "direction_id": direction_id,
        "trip_count": len(trips),
        "unique_shapes": sorted(list(set(shapes.values()))),
        "sample": list(shapes.items())[:5],
    }


# ---------------- ROUTE_SHAPES INDEX ---------------- #

@router.get("/route_shapes")
def debug_route_shapes_index():
    if not rt.route_shapes:
        return {"ok": False, "count": 0}

    return {
        "ok": True,
        "count": len(rt.route_shapes),
    }


@router.get("/route_shapes/sample")
def debug_route_shapes_sample():
    if not rt.route_shapes:
        return {"ok": False, "count": 0, "sample": None}

    keys = list(rt.route_shapes.keys())
    k = random.choice(keys)

    return {
        "ok": True,
        "count": len(keys),
        "sample_key": k,
        "sample_shape": rt.route_shapes[k],
    }
