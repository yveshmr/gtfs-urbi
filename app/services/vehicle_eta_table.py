from datetime import datetime, timedelta
from typing import Dict, Any

from app.core.state import rt
from pydantic import BaseModel

# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _get_shape_sequence_map(shape_id: str):
    # shape_id -> { stop_id: stop_sequence_index }
    return rt.shape_stop_sequence.get(shape_id)


def _find_current_index(vehicle: Dict[str, Any]):
    """
    Identifica índice do subtrecho usando stop_id atual.
    """
    shape_id = vehicle.get("shape_id")
    stop_id = vehicle.get("stop_id")

    if not shape_id or not stop_id:
        return None

    seq_map = _get_shape_sequence_map(shape_id)
    if not seq_map:
        return None

    # aqui é O(1)
    return seq_map.get(stop_id)

def _eta_state():
    """
    Estado em memória para estabilizar índice do subtrecho por veículo.
    """
    if not hasattr(rt, "vehicle_eta_state"):
        rt.vehicle_eta_state = {}
    return rt.vehicle_eta_state

def _get_shape_len_m(shape_id: str):
    """
    Tenta obter o comprimento do shape em metros, se existir no runtime.
    Não quebra se não existir.
    """
    # opções comuns (depende do seu runtime)
    for attr in ("shape_len_m", "shape_len_m_by_id", "shape_lengths_m", "shape_length_m"):
        if hasattr(rt, attr):
            val = getattr(rt, attr)
            # pode ser dict: {shape_id: len_m}
            if isinstance(val, dict) and shape_id in val:
                return val.get(shape_id)

    # pode estar em rt.route_shapes[shape_id] com campo len_m/length_m
    if hasattr(rt, "route_shapes") and isinstance(rt.route_shapes, dict):
        rs = rt.route_shapes.get(shape_id)
        if isinstance(rs, dict):
            return rs.get("len_m") or rs.get("length_m") or rs.get("shape_len_m")

    return None


# -------------------------------------------------------
# Tempo do subtrecho
# -------------------------------------------------------

def _subtrecho_time_seconds(s1, s2, speed_kmh):
    """
    Ordem:
    1) realtime stats
    2) histórico
    3) fallback velocidade
    """

    key = (s1, s2)

    # realtime (últimos 15 min)
    stats = rt.subtrecho_all_stats.get(key)
    if stats and stats.get("avg_time_sec"):
        return stats["avg_time_sec"], "realtime"

    # histórico
    hist = rt.historical_subtrechos.get(key)
    if hist and hist.get("avg_time_sec"):
        return hist["avg_time_sec"], "historical"

    # fallback velocidade
    distance_m = stats.get("distance_m") if stats else 300

    if not speed_kmh or speed_kmh <= 1:
        speed_kmh = 20

    speed_ms = speed_kmh / 3.6
    return distance_m / speed_ms, "fallback"


# -------------------------------------------------------
# ETA principal
# -------------------------------------------------------

def enrich_vehicle_with_eta(vehicle) -> Dict[str, Any]:
    # Aceita MapVehicle (Pydantic) ou dict
    if isinstance(vehicle, BaseModel):
        vehicle = vehicle.model_dump()   # se der erro, trocamos por vehicle.dict()

    # Identificador do veículo (pra manter estado)
    vehicle_id = vehicle.get("vehicle_id") or vehicle.get("id") or vehicle.get("vehicle_label")
    state = _eta_state()
    prev = state.get(vehicle_id) if vehicle_id else None

    shape_id = vehicle.get("shape_id")
    if not shape_id:
        return vehicle

    seq_map = _get_shape_sequence_map(shape_id)
    if not seq_map:
        return vehicle

    # lista de stop_ids ordenados por índice
    ordered_stop_ids = [sid for sid, _ in sorted(seq_map.items(), key=lambda kv: kv[1])]

    idx = _find_current_index(vehicle)

    # ---- HISTERese: nunca regredir ----
    if prev:
        prev_shape = prev.get("shape_id")
        prev_idx = prev.get("idx")

        # se shape mudou, reseta estado
        if prev_shape and prev_shape != shape_id:
            prev = None
            prev_idx = None

        # se não achou idx agora, mas já tinha um antes, mantém
        if idx is None and prev_idx is not None:
            idx = prev_idx

        # se achou idx mas ele regrediu, mantém o anterior
        if idx is not None and prev_idx is not None and idx < prev_idx:
            idx = prev_idx

    if idx is None:
        return vehicle

    # salva estado atualizado
    if vehicle_id:
        state[vehicle_id] = {"shape_id": shape_id, "idx": idx}

    vehicle["current_subtrecho_index"] = idx

    
    # ---- progress leve por índice (0..1) ----
    n = len(ordered_stop_ids)
    if n > 1:
        progress = idx / (n - 1)
        vehicle["progress"] = progress

        # ---- shape_pos_m leve (se houver comprimento do shape) ----
        shape_len_m = _get_shape_len_m(shape_id)
        if shape_len_m is not None:
            vehicle["shape_pos_m"] = float(shape_len_m) * float(progress)

    speed_kmh = vehicle.get("speed_kmh")

    total_sec = 0
    sources = {"realtime": 0, "historical": 0, "fallback": 0}

    for i in range(idx, len(ordered_stop_ids) - 1):
        s1 = ordered_stop_ids[i]
        s2 = ordered_stop_ids[i + 1]

        t, src = _subtrecho_time_seconds(s1, s2, speed_kmh)
        total_sec += t
        sources[src] += 1

    eta_ts = datetime.now() + timedelta(seconds=total_sec)

    vehicle["eta_seconds"] = int(total_sec)
    vehicle["eta_ts_iso"] = eta_ts.isoformat()
    vehicle["eta_sources"] = sources
    vehicle["remaining_subtrechos_count"] = len(ordered_stop_ids) - idx - 1

    return vehicle