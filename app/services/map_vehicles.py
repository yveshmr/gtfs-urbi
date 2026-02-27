from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel

from app.core.state import rt


class MapVehicle(BaseModel):
    """
    DTO enviado para o frontend na visão de MAPA.
    """

    vehicle_id: str
    vehicle_label: Optional[str]

    route_id: Optional[str]
    route_short_name: Optional[str]

    trip_id: Optional[str]
    direction_id: Optional[int]
    stop_id: Optional[str] = None
    lat: Optional[float]
    lon: Optional[float]

    shape_id: Optional[str]
    shape_pos_m: Optional[float]
    progress: Optional[float]

    speed_kmh: Optional[float]

    last_update_ts: Optional[datetime]

    status: str = "in_progress"

    # 👇👇👇 NOVO — heading calculado pelo backend
    heading_deg: Optional[float] = None

class MapVehicleTable(MapVehicle):
    """
    DTO enviado para o frontend na visão de TABELA.
    Herdamos tudo do MapVehicle e adicionamos as métricas calculadas.
    """
    current_subtrecho_index: Optional[int] = None
    remaining_subtrechos_count: Optional[int] = None
    eta_seconds: Optional[int] = None
    eta_ts_iso: Optional[str] = None
    eta_sources: Optional[dict] = None
    origin_stop_name: Optional[str] = None
    destination_stop_name: Optional[str] = None
    origin_stop_id: Optional[str] = None
    destination_stop_id: Optional[str] = None
    origin_stop_desc: Optional[str] = None
    destination_stop_desc: Optional[str] = None

def _safe(v: dict, key: str) -> Any:
    return v.get(key)



def _route_short_name(route_obj) -> Optional[str]:
    """
    Extrai route_short_name de forma segura
    tanto para objetos quanto para dicts.
    """
    if route_obj is None:
        return None

    if hasattr(route_obj, "route_short_name"):
        return getattr(route_obj, "route_short_name")

    if isinstance(route_obj, dict):
        return route_obj.get("route_short_name")

    return None



def get_active_map_vehicles() -> List[MapVehicle]:
    """
    Converte os veículos do backend realtime para um DTO
    amigável ao frontend de MAPA.
    """

    vehicles: List[MapVehicle] = []

    for v in rt.vehicles.values():

        route_id = _safe(v, "route_id")

        route = None
        if hasattr(rt, "routes") and route_id is not None:
            route = rt.routes.get(route_id)

        ts = _safe(v, "event_ts")
        last_update_dt = (
            datetime.fromtimestamp(ts)
            if ts is not None else None
        )

        mv = MapVehicle(
            vehicle_id=_safe(v, "vehicle_id") or _safe(v, "id"),
            vehicle_label=_safe(v, "vehicle_label") or _safe(v, "label"),
    
            route_id=route_id,
            route_short_name=_route_short_name(route),

            trip_id=_safe(v, "trip_id"),
            direction_id=_safe(v, "direction_id"),
            stop_id=_safe(v, "stop_id"),
            lat=_safe(v, "lat"),
            lon=_safe(v, "lon"),

            shape_id=_safe(v, "shape_id"),
            shape_pos_m=_safe(v, "shape_pos_m"),
            progress=_safe(v, "progress"),

            speed_kmh=_safe(v, "speed_kmh"),

            last_update_ts=last_update_dt,

            status=_safe(v, "status") or "in_progress",

            # 👇👇👇 AQUI PASSAMOS PRO FRONTEND
            heading_deg=_safe(v, "heading_deg"),
        )

        vehicles.append(mv)

    return vehicles
