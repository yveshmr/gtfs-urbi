from fastapi import APIRouter
from typing import List

from app.core.state import rt
from app.services.map_vehicles import MapVehicle, MapVehicleTable, get_active_map_vehicles
from app.services.vehicle_eta_table import enrich_vehicle_with_eta


router = APIRouter(
    prefix="/map",
    tags=["map"],
)


@router.get("/vehicles", response_model=List[MapVehicle])
def list_map_vehicles():
    return get_active_map_vehicles()


@router.get("/vehicles/table", response_model=List[MapVehicleTable])
def list_table_vehicles():
    base = get_active_map_vehicles()
    out = []

    for mv in base:
        d = mv.model_dump() if hasattr(mv, "model_dump") else mv.dict()

        # ETA
        d = enrich_vehicle_with_eta(d)

        # ORIGEM / DESTINO
        shape_id = d.get("shape_id")

        if shape_id:
            seq_map = rt.shape_stop_sequence.get(shape_id)

            if seq_map:
                ordered = sorted(seq_map.items(), key=lambda kv: kv[1])
                first_stop_id = ordered[0][0]
                last_stop_id = ordered[-1][0]

                d["origin_stop_id"] = first_stop_id
                d["destination_stop_id"] = last_stop_id

                stop_info = getattr(rt, "stop_info", None)

                if isinstance(stop_info, dict):
                    origin_info = stop_info.get(first_stop_id, {})
                    dest_info = stop_info.get(last_stop_id, {})

                    d["origin_stop_name"] = origin_info.get("stop_name")
                    d["origin_stop_desc"] = origin_info.get("stop_desc")

                    d["destination_stop_name"] = dest_info.get("stop_name")
                    d["destination_stop_desc"] = dest_info.get("stop_desc")

        out.append(d)

    return out