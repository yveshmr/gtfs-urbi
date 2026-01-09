from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import time

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

# ================= PIPELINE SUBTRECHOS =================
from gtfs_core.pipeline_trechos import construir_todos_os_subtrechos
from app.services.realtime_subtrechos import build_subtrecho_index

# ================= SHAPE → STOP SEQUENCE =================
from app.services.shape_stop_sequence import build_shape_stop_sequence

# ================= MAPA =================
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


# =========================================================
# LOOP DE VEÍCULOS (POOLING = 10s — igual ao monolítico)
# =========================================================
async def vehicles_loop():
    while True:
        try:
            update_vehicles()
        except Exception as e:
            print("⚠ vehicle loop error:", e)

        await asyncio.sleep(10)


# =========================================================
# STARTUP
# =========================================================
@app.on_event("startup")
def startup():

    print("🔹 Starting GTFS Live backend...")

    # -----------------------------------------------------
    # 1 — GTFS ESTÁTICO
    # -----------------------------------------------------
    ensure_gtfs_static()

    # -----------------------------------------------------
    # 2 — SHAPES
    # -----------------------------------------------------
    print("⏳ carregando shapes ...")
    rt.shapes = load_shapes()
    print(f"✔ shapes carregados: {len(rt.shapes)}")

    # -----------------------------------------------------
    # 3 — STOP_TIMES
    # -----------------------------------------------------
    print("⏳ carregando stop_times ...")
    rt.stop_times = load_stop_times()
    print(f"✔ stop_times carregados: {len(rt.stop_times)} trips")

    # -----------------------------------------------------
    # 4 — STOPS
    # -----------------------------------------------------
    print("⏳ carregando stops ...")
    rt.stops = load_stops()
    print(f"✔ stops carregados: {len(rt.stops)}")

    # -----------------------------------------------------
    # 5 — ROUTES
    # -----------------------------------------------------
    print("⏳ carregando routes ...")
    rt.routes = load_routes()
    print(f"✔ routes carregadas: {len(rt.routes)}")

    # -----------------------------------------------------
    # 6 — TRIPS
    # -----------------------------------------------------
    print("⏳ carregando trips ...")
    rt.trips = load_trips()
    print(f"✔ trips carregadas: {len(rt.trips)}")

    # -----------------------------------------------------
    # 7 — ROUTE → DIRECTION → SHAPE
    # (SEM fallback de direction_id)
    # -----------------------------------------------------
    rt.route_shapes = build_route_shape_index(rt.trips)
    print(f"✔ route_shapes criado: {len(rt.route_shapes)} combinações")

    # -----------------------------------------------------
    # 7.1 — SHAPE → STOP_SEQUENCE (MONOLÍTICO)
    # -----------------------------------------------------
    print("⏳ construindo shape_stop_sequence ...")
    build_shape_stop_sequence()
    print(f"✔ shape_stop_sequence criado: {len(rt.shape_stop_sequence)} shapes")

    # -----------------------------------------------------
    # 7.2 — SUBTRECHOS (PIPELINE GTFS)
    # -----------------------------------------------------
    print("⏳ construindo subtrechos (pipeline GTFS)...")
    try:
        rt.subtrechos = construir_todos_os_subtrechos()
        print(f"✔ subtrechos gerados: {len(rt.subtrechos)}")

        build_subtrecho_index()
        print("✔ índice de subtrechos por shape criado")

    except Exception as e:
        print(f"⚠️ Falha ao gerar subtrechos: {e}")
        rt.subtrechos = []

    # -----------------------------------------------------
    # 8 — PRIMEIRA CARGA DE VEÍCULOS
    # -----------------------------------------------------
    update_vehicles()

    print("Startup complete")
    print(f"Stops: {len(rt.stops)}")
    print(f"Routes: {len(rt.routes)}")
    print(f"Trips: {len(rt.trips)}")
    print(f"Stop times: {len(rt.stop_times)}")
    print(f"Shapes: {len(rt.shapes)}")
    print(f"Subtrechos: {len(rt.subtrechos)}")
    print(f"Vehicles: {len(rt.vehicles)}")

    print("INFO: Application startup complete.")

    # -----------------------------------------------------
    # LOOP DE SNAPSHOT (CSV)
    # -----------------------------------------------------
    asyncio.create_task(persist_subtrechos_loop())

    # -----------------------------------------------------
    # LOOP DE VEÍCULOS
    # -----------------------------------------------------
    asyncio.create_task(vehicles_loop())


# =========================================================
# ROUTERS
# =========================================================
app.include_router(debug_router)
app.include_router(map_router)
app.include_router(map_shapes_router)
app.include_router(map_routes_router)
app.include_router(map_subtrechos_stop_router)
app.include_router(map_subtrechos_shape_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "gtfs-live-backend"}


# =========================================================
# HEALTH
# =========================================================
AVG_WINDOW_SEC = 900  # 15 minutos


@app.get("/health", response_class=JSONResponse)
def health():

    now = int(time.time())
    cutoff = now - AVG_WINDOW_SEC

    total_keys = len(getattr(rt, "subtrecho_times_by_shape", {}))

    segments_recent = 0
    measurements_recent = 0

    for lst in getattr(rt, "subtrecho_times_by_shape", {}).values():
        recent = [m for m in lst if m["end_ts"] >= cutoff]
        if recent:
            segments_recent += 1
            measurements_recent += len(recent)

    avg_samples = (
        measurements_recent / segments_recent
        if segments_recent > 0 else 0
    )

    return {
        "status": "ok",
        "vehicles_total": len(rt.vehicles),
        "subtrechos": {
            "total_keys": total_keys,
            "segments_with_data_last_15m": segments_recent,
            "measurements_last_15m": measurements_recent,
            "avg_samples_per_segment": round(avg_samples, 2),
        }
    }
