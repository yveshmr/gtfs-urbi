from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio

from geopy.distance import geodesic

from app.core.state import rt

from app.services.gtfs_static import ensure_gtfs_static
from app.services.shapes_loader import load_shapes
from app.services.stop_times_loader import load_stop_times
from app.services.trip_lookup import load_trips, build_route_shape_index
from app.services.stops_loader import load_stops
from app.services.routes_loader import load_routes
from app.services.vehicles import update_vehicles
from app.services.subtrecho_persistence import persist_subtrechos_loop

from app.services.subtrechos_all_builder import build_all_subtrechos
from app.services.shape_stop_sequence import build_shape_stop_sequence
from app.services.historical_subtrechos_builder import build_historical_subtrechos

from app.api.debug import router as debug_router
from app.api.map import router as map_router
from app.api.map_shapes import router as map_shapes_router
from app.api.map_routes import router as map_routes_router
from app.api.map_subtrechos_stop import router as map_subtrechos_stop_router
from app.api.map_subtrechos_shape import router as map_subtrechos_shape_router
from app.api.map_subtrechos_all_speed import router as map_subtrechos_all_speed_router
from app.api.map_subtrechos_pairs import router as map_subtrechos_pairs_router
from app.api.map_subtrechos_comparison import router as map_subtrechos_comparison_router


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


async def vehicles_loop():
    while True:
        try:
            update_vehicles()
        except Exception as e:
            print("⚠ vehicle loop error:", e)
        await asyncio.sleep(10)


@app.on_event("startup")
def startup():

    print("🔹 Starting GTFS Live backend...")

    ensure_gtfs_static()

    print("⏳ carregando shapes ...")
    raw_shapes = load_shapes()

    norm_shapes = {}
    for shape_id, pts in raw_shapes.items():
        acc = 0.0
        out = []
        prev = None

        for p in pts:
            lat = float(p["lat"])
            lon = float(p["lon"])

            if prev:
                acc += geodesic(prev, (lat, lon)).meters

            out.append((lat, lon, acc))
            prev = (lat, lon)

        norm_shapes[shape_id] = out

    rt.shapes = norm_shapes
    print(f"✔ shapes normalizados: {len(rt.shapes)}")

    print("⏳ carregando stop_times ...")
    rt.stop_times = load_stop_times()
    print(f"✔ stop_times carregados: {len(rt.stop_times)} trips")

    print("⏳ carregando stops ...")
    raw_stops = load_stops()

    rt.stops = {
        sid: (float(s["stop_lat"]), float(s["stop_lon"]))
        for sid, s in raw_stops.items()
    }

    rt.stop_info = {
        sid: {
            "stop_name": (s.get("stop_name") or "").strip() or None,
            "stop_desc": (s.get("stop_desc") or "").strip() or None,
        }
        for sid, s in raw_stops.items()
    }

    print(f"✔ stops normalizados: {len(rt.stops)}")
    print(f"✔ stop_names carregados: {len(rt.stop_info)}")

    print("⏳ carregando routes ...")
    rt.routes = load_routes()
    print(f"✔ routes carregadas: {len(rt.routes)}")

    print("⏳ carregando trips ...")
    rt.trips = load_trips()
    print(f"✔ trips carregadas: {len(rt.trips)}")

    rt.route_shapes = build_route_shape_index(rt.trips)

    print("⏳ construindo shape_stop_sequence ...")
    build_shape_stop_sequence()

    print("⏳ construindo subtrechos ALL ...")
    rt.subtrechos_all = build_all_subtrechos()

    print("⏳ construindo base histórica ...")
    build_historical_subtrechos()

    update_vehicles()

    asyncio.create_task(persist_subtrechos_loop())
    asyncio.create_task(vehicles_loop())


app.include_router(debug_router)
app.include_router(map_router)
app.include_router(map_shapes_router)
app.include_router(map_routes_router)
app.include_router(map_subtrechos_stop_router)
app.include_router(map_subtrechos_shape_router)
app.include_router(map_subtrechos_all_speed_router)
app.include_router(map_subtrechos_pairs_router)
app.include_router(map_subtrechos_comparison_router)


@app.get("/health", response_class=JSONResponse)
def health():
    return {
        "status": "ok",
        "vehicles": len(rt.vehicles),
        "subtrechos_all": len(rt.subtrechos_all),
    }