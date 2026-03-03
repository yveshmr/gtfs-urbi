import os
from datetime import datetime, timedelta
from app.integrations.cittati.client import CittatiClient
from app.integrations.cittati.cache import escolher_viagem_ativa_por_prefixo

from fastapi import APIRouter
from typing import List

from app.core.state import rt
from app.services.map_vehicles import MapVehicle, MapVehicleTable, get_active_map_vehicles
from app.services.vehicle_eta_table import enrich_vehicle_with_eta


router = APIRouter(
    prefix="/map",
    tags=["map"],
)

def _get_cittati_client():
    # cria 1 client e reaproveita (cache em memória)
    if hasattr(rt, "_cittati_client"):
        return getattr(rt, "_cittati_client")

    user = os.getenv("CITTATI_USER")
    pwd = os.getenv("CITTATI_PASS")

    if not user or not pwd:
        setattr(rt, "_cittati_client", None)
        return None

    client = CittatiClient(user, pwd, timeout=20)
    setattr(rt, "_cittati_client", client)
    return client


def _get_cittati_ativas_por_prefixo(data_ddmmyyyy: str):
    """
    Retorna dict: { "336076": {campos...}, ... } apenas para viagens ativas/prováveis.
    Cache curto (30s) pra não martelar o WS.
    """
    now = datetime.now()

    cache = getattr(rt, "_cittati_cache", None)
    if cache:
        if cache.get("data") == data_ddmmyyyy and cache.get("exp", now) > now:
            return cache.get("by_prefixo") or {}

    client = _get_cittati_client()
    if client is None:
        return {}

    payload = client.consultar_viagens(data_ddmmyyyy=data_ddmmyyyy)
    by_prefixo = escolher_viagem_ativa_por_prefixo(payload, now=now)

    setattr(rt, "_cittati_cache", {
        "data": data_ddmmyyyy,
        "by_prefixo": by_prefixo,
        "exp": now + timedelta(seconds=30),
    })

    return by_prefixo

@router.get("/vehicles", response_model=List[MapVehicle])
def list_map_vehicles():
    return get_active_map_vehicles()


@router.get("/vehicles/table", response_model=List[MapVehicleTable])
def list_table_vehicles():
    base = get_active_map_vehicles()
    out = []

    data_ddmmyyyy = datetime.now().strftime("%d/%m/%Y")
    ativas_por_prefixo = _get_cittati_ativas_por_prefixo(data_ddmmyyyy)

    for mv in base:
        d = mv.model_dump() if hasattr(mv, "model_dump") else mv.dict()

        # ETA
        d = enrich_vehicle_with_eta(d)

        # ORIGEM / DESTINO
        shape_id = d.get("shape_id")

        # ===== CITTATI: join por prefixo (vehicle_label <-> veiculo) =====
        prefixo = (d.get("vehicle_label") or "").strip()
        if prefixo and prefixo in ativas_por_prefixo:
            v = ativas_por_prefixo[prefixo]

            d["inicioProgramado"] = v.get("inicioProgramado")
            d["inicioRealizado"] = v.get("inicioRealizado")
            d["fimProgramado"] = v.get("fimProgramado")

            d["nomePontoInicio"] = v.get("nomePontoInicio")
            d["nomePontoFim"] = v.get("nomePontoFim")

            d["codAtendimento"] = v.get("codAtendimento")
            d["atividade"] = v.get("atividade")
            d["tabela"] = v.get("tabela")

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