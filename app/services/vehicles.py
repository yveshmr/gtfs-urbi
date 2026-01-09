import time
import httpx
from collections import defaultdict

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from google.transit import gtfs_realtime_pb2


AVG_WINDOW_SEC = 900      # 15 minutos
MIN_GAP_SEC = 3           # mínimo entre travessias


def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None
        return round(speed_raw, 1)
    except Exception:
        return None


def prune_old_measurements(now_ts: int):
    cutoff = now_ts - AVG_WINDOW_SEC

    store = getattr(rt, "subtrecho_times", None)
    if not store:
        return

    for key, lst in list(store.items()):
        new_lst = [m for m in lst if m["end_ts"] >= cutoff]
        if new_lst:
            store[key] = new_lst
        else:
            store.pop(key, None)


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

    # =====================================================
    # ESTADOS (IGUAL AO MONOLÍTICO)
    # =====================================================

    if not hasattr(rt, "vehicle_last_stop"):
        rt.vehicle_last_stop = {}

    if not hasattr(rt, "subtrecho_times"):
        rt.subtrecho_times = defaultdict(list)

    if not hasattr(rt, "subtrecho_stats"):
        rt.subtrecho_stats = {}

    prune_old_measurements(now)

    # =====================================================
    # LOOP GTFS-RT
    # =====================================================

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

        # 🔴 REGRA CORRETA — direction_id SOMENTE se existir
        direction_id = (
            trip.direction_id
            if trip.HasField("direction_id")
            else None
        )

        ts = veh.timestamp or now

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
            "status": "on_route" if route_id else "off_route",
        }

        # =================================================
        # 🚦 MODELO MONOLÍTICO — STOP → STOP CONTÍNUO
        # =================================================
        if stop_id and route_id and direction_id is not None:

            key = f"{route_id}_{direction_id}"
            shape_id = rt.route_shapes.get(key)

            if shape_id and shape_id in rt.shape_stop_sequence:

                stop_seq_map = rt.shape_stop_sequence[shape_id]
                if stop_id in stop_seq_map:

                    cur_seq = stop_seq_map[stop_id]

                    prev = rt.vehicle_last_stop.get(vehicle_id)

                    if (
                        prev
                        and prev["shape_id"] == shape_id
                        and cur_seq == prev["stop_seq"] + 1
                    ):
                        s1 = prev["stop_id"]
                        s2 = stop_id
                        st_key = (s1, s2)

                        # subtrecho existe?
                        st = next(
                            (x for x in rt.subtrechos if x.s1 == s1 and x.s2 == s2),
                            None
                        )

                        if st:
                            dt = ts - prev["ts"]

                            if dt >= MIN_GAP_SEC:
                                speed_kmh = (st.distance_m / dt) * 3.6

                                rt.subtrecho_times[st_key].append({
                                    "speed_kmh": speed_kmh,
                                    "end_ts": ts,
                                })

                                vals = rt.subtrecho_times[st_key]
                                avg = sum(m["speed_kmh"] for m in vals) / len(vals)

                                rt.subtrecho_stats[st_key] = {
                                    "speed_avg_kmh": round(avg, 1),
                                    "n": len(vals),
                                    "last_ts": ts,
                                }

                    # atualiza estado
                    rt.vehicle_last_stop[vehicle_id] = {
                        "shape_id": shape_id,
                        "stop_id": stop_id,
                        "stop_seq": cur_seq,
                        "ts": ts,
                    }

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
