import time
import httpx
from collections import defaultdict

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from google.transit import gtfs_realtime_pb2
from geopy.distance import geodesic


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


def _iter_shape_points(shape_pts):
    """
    Normaliza shape points para (lat, lon, m).

    Aceita:
      - dict: {lat, lon, seq}  (sem metragem)
      - tuple: (lat, lon, m)
    """
    acc = 0.0
    prev = None

    for p in shape_pts:

        if isinstance(p, dict):
            lat = float(p["lat"])
            lon = float(p["lon"])

            if prev:
                acc += geodesic(prev, (lat, lon)).meters

            yield lat, lon, acc
            prev = (lat, lon)

        else:
            # assume (lat, lon, m)
            yield p


def measure_along_shape(shape_pts, lat, lon):
    """
    Retorna a metragem acumulada no ponto mais próximo do shape
    """
    best = None
    best_m = None

    for la, lo, m in _iter_shape_points(shape_pts):
        d = geodesic((la, lo), (lat, lon)).meters
        if best is None or d < best:
            best = d
            best_m = m

    return best_m


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

    if not hasattr(rt, "vehicle_last_stop"):
        rt.vehicle_last_stop = {}

    if not hasattr(rt, "subtrecho_times"):
        rt.subtrecho_times = defaultdict(list)

    if not hasattr(rt, "subtrecho_stats"):
        rt.subtrecho_stats = {}

    prune_old_measurements(now)

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

        lat = pos.latitude if pos.HasField("latitude") else None
        lon = pos.longitude if pos.HasField("longitude") else None

        v = {
            "vehicle_id": vehicle_id,
            "vehicle_label": desc.label or None,
            "lat": lat,
            "lon": lon,
            "speed_kmh": parse_speed(pos.speed if pos.HasField("speed") else None),
            "event_ts": ts,
            "route_id": route_id,
            "direction_id": direction_id,
            "stop_id": stop_id,
            "shape_id": None,
            "shape_pos_m": None,
            "progress": None,
            "status": "on_route" if route_id else "off_route",
        }

        if route_id and direction_id is not None and lat is not None and lon is not None:

            key = f"{route_id}_{direction_id}"
            shape_id = rt.route_shapes.get(key)

            if shape_id and shape_id in rt.shapes:

                shape_pts = rt.shapes[shape_id]
                shape_pos_m = measure_along_shape(shape_pts, lat, lon)

                total_m = None
                for _, _, m in _iter_shape_points(shape_pts):
                    total_m = m

                v["shape_id"] = shape_id
                v["shape_pos_m"] = shape_pos_m

                if total_m and shape_pos_m is not None:
                    v["progress"] = round(shape_pos_m / total_m, 4)

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
