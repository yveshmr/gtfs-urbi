import time
import httpx
from collections import defaultdict
from datetime import datetime

from google.transit import gtfs_realtime_pb2

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from app.services.subtrechos_comparator import compare_realtime_with_historical


AVG_WINDOW_SEC = 900   # 15 minutos
MIN_GAP_SEC = 3        # mínimo entre medições

MAX_SPEED_KMH = 70.0   # ✅ corte solicitado


# =====================================================
# UTIL
# =====================================================

def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None
        return round(speed_raw, 1)
    except Exception:
        return None


def prune_old_measurements(store: dict, now_ts: int):
    cutoff = now_ts - AVG_WINDOW_SEC

    for key, lst in list(store.items()):
        lst = [m for m in lst if m["end_ts"] >= cutoff]
        if lst:
            store[key] = lst
        else:
            store.pop(key, None)


# =====================================================
# UPDATE VEHICLES
# =====================================================

def update_vehicles():

    feed = gtfs_realtime_pb2.FeedMessage()

    try:
        resp = httpx.get(URL_VEHICLE_POSITIONS, timeout=20)
        resp.raise_for_status()
        feed.ParseFromString(resp.content)
    except Exception as e:
        print(f"⚠️ Falha ao baixar/parsing GTFS-RT vehicles: {e}")
        return

    now = int(time.time())
    vehicles = {}

    # ================= RUNTIME STATE =================

    if not hasattr(rt, "vehicle_last_stop"):
        rt.vehicle_last_stop = {}

    if not hasattr(rt, "subtrecho_all_times"):
        rt.subtrecho_all_times = defaultdict(list)

    if not hasattr(rt, "subtrecho_all_stats"):
        rt.subtrecho_all_stats = {}

    prune_old_measurements(rt.subtrecho_all_times, now)

    # ================= LOOP GTFS-RT =================

    for entity in feed.entity:

        if not entity.HasField("vehicle"):
            continue

        veh = entity.vehicle
        desc = veh.vehicle
        trip = veh.trip
        pos = veh.position

        vehicle_id = desc.id
        if not vehicle_id:
            continue

        stop_id = veh.stop_id or None
        route_id = trip.route_id or None

        direction_id = (
            trip.direction_id
            if trip.HasField("direction_id")
            else None
        )

        ts = veh.timestamp or now

        # ================= SHAPE RESOLUTION =================

        shape_id = None
        if route_id and direction_id is not None:
            shape_id = rt.route_shapes.get(f"{route_id}_{direction_id}")

        v = {
            "vehicle_id": vehicle_id,
            "vehicle_label": desc.label or None,
            "lat": pos.latitude if pos.HasField("latitude") else None,
            "lon": pos.longitude if pos.HasField("longitude") else None,
            "speed_kmh": parse_speed(pos.speed if pos.HasField("speed") else None),
            "event_ts": ts,
            "route_id": route_id,
            "direction_id": direction_id,
            "stop_id": stop_id,
            "shape_id": shape_id,
            "status": "on_route" if route_id else "off_route",
        }

        # =====================================================
        # VELOCIDADE POR SUBTRECHO (ALL — GLOBAL)
        # =====================================================

        if stop_id and shape_id and shape_id in rt.shape_stop_sequence:

            seq_map = rt.shape_stop_sequence[shape_id]

            if stop_id in seq_map:

                cur_seq = seq_map[stop_id]
                prev = rt.vehicle_last_stop.get(vehicle_id)

                # --- SOMENTE A -> B CONSECUTIVO ---
                if (
                    prev
                    and prev["shape_id"] == shape_id
                    and cur_seq == prev["stop_seq"] + 1
                ):
                    sA = prev["stop_id"]
                    sB = stop_id
                    dt = ts - prev["ts"]

                    if dt >= MIN_GAP_SEC:

                        key = (str(sA), str(sB))
                        st = rt.subtrechos_all.get(key)

                        if st:
                            distance_m = float(st.distance_m)
                            speed_last_kmh = (distance_m / dt) * 3.6

                            # =================================================
                            # ✅ CORTE DE OUTLIER (ex: > 70 km/h)
                            # =================================================
                            if speed_last_kmh > MAX_SPEED_KMH:
                                # salva um “evento de descarte” pro frontend exibir no popup
                                rt.subtrecho_all_stats[key] = {
                                    # mantém o que já tínhamos, se existir (pra não zerar a camada)
                                    **rt.subtrecho_all_stats.get(key, {}),

                                    # debug do cálculo descartado
                                    "distance_m": round(distance_m, 2),
                                    "dt_sec": int(dt),
                                    "speed_last_kmh": round(speed_last_kmh, 1),
                                    "t0_ts": int(prev["ts"]),
                                    "t1_ts": int(ts),

                                    # info de descarte
                                    "discarded": {
                                        "reason": "speed_cutoff",
                                        "max_speed_kmh": MAX_SPEED_KMH,
                                        "speed_last_kmh": round(speed_last_kmh, 1),
                                        "ts": int(ts),
                                    },
                                }

                                # não entra na janela, não recalcula média
                                rt.vehicle_last_stop[vehicle_id] = {
                                    "shape_id": shape_id,
                                    "stop_id": stop_id,
                                    "stop_seq": cur_seq,
                                    "ts": ts,
                                }

                                vehicles[vehicle_id] = v
                                continue

                            # =================================================
                            # ✅ MEDIÇÃO VÁLIDA → entra na janela
                            # =================================================
                            rt.subtrecho_all_times[key].append({
                                "speed_kmh": speed_last_kmh,
                                "end_ts": ts,
                            })

                            vals = rt.subtrecho_all_times[key]
                            avg = sum(m["speed_kmh"] for m in vals) / len(vals)

                            comparison = compare_realtime_with_historical(
                                s1=str(sA),
                                s2=str(sB),
                                realtime_speed_kmh=avg,
                                realtime_timestamp_utc=datetime.utcfromtimestamp(ts),
                            )

                            rt.subtrecho_all_stats[key] = {
                                # métricas agregadas
                                "speed_avg_kmh": round(avg, 1),
                                "n": len(vals),
                                "last_ts": ts,

                                # insumos do cálculo (debug no frontend)
                                "distance_m": round(distance_m, 2),
                                "dt_sec": int(dt),
                                "speed_last_kmh": round(speed_last_kmh, 1),
                                "t0_ts": int(prev["ts"]),
                                "t1_ts": int(ts),

                                # comparação
                                "comparison": comparison,

                                # se antes teve descarte, zera o aviso quando tiver medição boa
                                "discarded": None,
                            }

                # --- ATUALIZA ESTADO DO VEÍCULO ---
                rt.vehicle_last_stop[vehicle_id] = {
                    "shape_id": shape_id,
                    "stop_id": stop_id,
                    "stop_seq": cur_seq,
                    "ts": ts,
                }

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
