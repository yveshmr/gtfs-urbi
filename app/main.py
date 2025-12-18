from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.debug import router as debug_router
from app.core.state import rt
from app.static.stops import load_stops

app = FastAPI(title="GTFS Live")

@app.on_event("startup")
def startup():
    rt.stops = load_stops()

app.include_router(health_router)
app.include_router(debug_router)
