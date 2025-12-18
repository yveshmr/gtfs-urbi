from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.debug import router as debug_router
from app.core.state import rt
from app.static.stops import load_stops
from app.static.routes import load_routes
from app.static.trips import load_trips
from app.static.stop_times import load_stop_times
from app.static.segments import build_segments
from app.services.gtfs_static import ensure_gtfs_static
from app.services.vehicles import update_vehicles




app = FastAPI(title="GTFS Live")

@app.on_event("startup")
async def startup():
    ensure_gtfs_static()
    rt.stops = load_stops()
    rt.routes = load_routes()
    rt.trips = load_trips()
    rt.stop_times = load_stop_times()
    rt.segments = build_segments(rt)
    update_vehicles()
    print("Vehicles loaded:", len(rt.vehicles))
    print("Stops:", len(rt.stops))
    print("Trips:", len(rt.trips))
    print("Stop times:", len(rt.stop_times))
    print("Segments:", len(rt.segments))





app.include_router(health_router)
app.include_router(debug_router)
