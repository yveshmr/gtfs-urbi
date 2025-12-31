import time

def compute_vehicle_eta(vehicle: dict):
    """
    Retorna ETA simples baseado na distância restante do shape
    e velocidade atual.
    """

    try:
        if (
            not vehicle
            or vehicle.get("status") != "on_route"
            or vehicle.get("shape_len_m") in (None, 0)
            or vehicle.get("shape_pos_m") is None
            or vehicle.get("speed_kmh") in (None, 0)
        ):
            return None

        dist_total = vehicle["shape_len_m"]
        dist_done = vehicle["shape_pos_m"]

        # segurança
        if dist_done >= dist_total:
            return None

        dist_remaining = dist_total - dist_done  # metros
        speed_ms = vehicle["speed_kmh"] / 3.6

        if speed_ms <= 0:
            return None

        eta_seconds = dist_remaining / speed_ms
        eta_ts = int(time.time() + eta_seconds)

        return {
            "eta_ts": eta_ts,
            "eta_seconds": int(eta_seconds),
            "dist_remaining_m": round(dist_remaining, 1),
        }

    except Exception as e:
        print(f"⚠ ETA calc error: {e}")
        return None
