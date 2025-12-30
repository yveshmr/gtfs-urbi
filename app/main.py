from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.state import rt
from app.services.gtfs_static import ensure_gtfs_static
from app.services.shapes_loader import load_shapes
from app.services.stop_times_loader import load_stop_times
from app.services.trip_lookup import load_trips, build_route_shape_index
from app.services.stops_loader import load_stops
from app.services.routes_loader import load_routes
from app.services.vehicles import update_vehicles

from app.api.debug import router as debug_router


app = FastAPI(
    title="GTFS Live Backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():

    print("🔹 Starting GTFS Live backend...")

    #
    # 1 — garantir GTFS estático
    #
    ensure_gtfs_static()

    #
    # 2 — carregar shapes
    #
    print("⏳ carregando shapes ...")
    rt.shapes = load_shapes()
    print(f"✔ shapes carregados: {len(rt.shapes)}")

    #
    # 3 — carregar stop_times
    #
    print("⏳ carregando stop_times ...")
    rt.stop_times = load_stop_times()
    print(f"✔ stop_times carregados: {len(rt.stop_times)} trips com horários")

    #
    # 4 — carregar stops
    #
    print("⏳ carregando stops ...")
    rt.stops = load_stops()
    print(f"✔ stops carregados: {len(rt.stops)}")

    #
    # 5 — carregar routes
    #
    print("⏳ carregando routes ...")
    rt.routes = load_routes()
    print(f"✔ routes carregadas: {len(rt.routes)}")

    #
    # 6 — carregar trips
    #
    print("⏳ carregando trips ...")
    rt.trips = load_trips()
    print(f"✔ trips carregadas: {len(rt.trips)}")

    #
    # 7 — construir route→direction→shape
    #
    rt.route_shapes = build_route_shape_index(rt.trips)
    print(f"✔ route_shapes criado: {len(rt.route_shapes)} combinações")

    #
    # 8 — puxar vehicles GTFS-RT
    #
    update_vehicles()

    print("Startup complete")
    print(f"Stops: {len(rt.stops)}")
    print(f"Routes: {len(rt.routes)}")
    print(f"Trips: {len(rt.trips)}")
    print(f"Stop times: {len(rt.stop_times)}")
    print(f"Shapes: {len(rt.shapes)}")
    print(f"Vehicles: {len(rt.vehicles)}")

    print("INFO:     Application startup complete.")


#
# DEBUG ROUTES
#
app.include_router(debug_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "gtfs-live-backend"}
