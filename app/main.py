from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import time

from geopy.distance import geodesic

from app.core.state import rt
from app.services.gtfs_static import ensure_gtfs_static
from app.services.shapes_loader import load_shapes
from app.services.stop_times_loader import load_stop_times
from app.services.trip_lookup import load_trips, build_route_shape_index
from app.services.stops_loader import load_stops
from app.services.routes_loader import load_routes
from app.services.vehicles import update_vehicles
from app.api.debug import router as debug_router
from app.services.subtrecho_persistence import persist_subtrechos_loop

from gtfs_core.pipeline_trechos import construir_todos_os_subtrechos
from app.services.realtime_subtrechos import build_subtrecho_index
from app.services.shape_stop_sequence import build_shape_stop_sequence

from app.api.map import router as map_router
from app.api.map_shapes import router as map_shapes_router
from app.api.map_routes import router as map_routes_router
from app.api.map_subtrechos_stop import router as map_subtrechos_stop_router
from app.api.map_subtrechos_shape import router as map_subtrechos_shape_router


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

    # 1 — GTFS
    ensure_gtfs_static()

    # 2 — SHAPES (NORMALIZADO)
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

    # 3 — STOP_TIMES
    print("⏳ carregando stop_times ...")
    rt.stop_times = load_stop_times()
    print(f"✔ stop_times carregados: {len(rt.stop_times)} trips")

    # 4 — STOPS (🔥 NORMALIZAÇÃO CRÍTICA 🔥)
    print("⏳ carregando stops ...")
    raw_stops = load_stops()

    norm_stops = {}
    for stop_id, s in raw_stops.items():
        lat = float(s["stop_lat"])
        lon = float(s["stop_lon"])
        norm_stops[stop_id] = (lat, lon)

    rt.stops = norm_stops
    print(f"✔ stops normalizados: {len(rt.stops)}")

    # 5 — ROUTES
    print("⏳ carregando routes ...")
    rt.routes = load_routes()
    print(f"✔ routes carregadas: {len(rt.routes)}")

    # 6 — TRIPS
    print("⏳ carregando trips ...")
    rt.trips = load_trips()
    print(f"✔ trips carregadas: {len(rt.trips)}")

    # 7 — ROUTE → SHAPE
    rt.route_shapes = build_route_shape_index(rt.trips)
    print(f"✔ route_shapes criado: {len(rt.route_shapes)} combinações")

    # 7.1 — SHAPE → STOP_SEQUENCE
    print("⏳ construindo shape_stop_sequence ...")
    build_shape_stop_sequence()
    print(f"✔ shape_stop_sequence criado: {len(rt.shape_stop_sequence)} shapes")

    # 7.2 — SUBTRECHOS
    print("⏳ construindo subtrechos (pipeline GTFS)...")
    try:
        rt.subtrechos = construir_todos_os_subtrechos()
        print(f"✔ subtrechos gerados: {len(rt.subtrechos)}")
        build_subtrecho_index()
    except Exception as e:
        print(f"⚠️ Falha ao gerar subtrechos: {e}")
        rt.subtrechos = []

    update_vehicles()

    print("Startup complete")
    print(f"Subtrechos: {len(rt.subtrechos)}")

    asyncio.create_task(persist_subtrechos_loop())
    asyncio.create_task(vehicles_loop())


app.include_router(debug_router)
app.include_router(map_router)
app.include_router(map_shapes_router)
app.include_router(map_routes_router)
app.include_router(map_subtrechos_stop_router)
app.include_router(map_subtrechos_shape_router)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health", response_class=JSONResponse)
def health():
    return {"status": "ok", "vehicles": len(rt.vehicles)}
