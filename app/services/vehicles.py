import time
import httpx
import math

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from app.geometry.shape_positioning import project_vehicle_shape_position
from app.services.vehicle_progress import compute_shape_length
from app.services.realtime_subtrechos import find_subtrecho_for_position

from google.transit import gtfs_realtime_pb2


AVG_WINDOW_SEC = 900  # 10 min
HEADING_RADIUS_M = 15.0


def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None
        return round(speed_raw, 1)
    except:
        return None


#
# ========= HEADING CARTESIANO A PARTIR DO SHAPE =========
#
def compute_heading_from_shape(points, pos_m, radius_m=HEADING_RADIUS_M):
    """
    Heading cartesiano puro, baseado no segmento do shape
    que cruza um raio em torno da posição projetada.

    - Usa apenas geometria local
    - Respeita o sentido crescente do shape
    - NÃO aplica correções de eixo (Leaflet, norte, etc.)
    """

    if not points or pos_m is None:
        return None

    pos_m = float(pos_m)

    # coletar segmentos que cruzam o intervalo [pos_m - R, pos_m + R]
    candidates = []

    for i in range(len(points) - 1):
        lat1, lon1, d1 = points[i]
        lat2, lon2, d2 = points[i + 1]

        # verifica interseção do segmento com o intervalo
        if d2 < pos_m - radius_m:
            continue
        if d1 > pos_m + radius_m:
            break

        candidates.append((lat1, lon1, lat2, lon2, d1, d2))

    if not candidates:
        return None

    # escolher o segmento mais próximo à posição projetada
    seg = min(
        candidates,
        key=lambda s: abs(((s[4] + s[5]) / 2.0) - pos_m)
    )

    lat1, lon1, lat2, lon2, _, _ = seg

    dx = lon2 - lon1
    dy = lat2 - lat1

    if dx == 0 and dy == 0:
        return None

    heading = math.degrees(math.atan2(dy, dx))
    return round(heading, 2)


def prune_old_measurements(now_ts: int):
    cutoff = now_ts - AVG_WINDOW_SEC

    for key, lst in list(rt.subtrecho_times.items()):
        new_lst = [m for m in lst if m["end_ts"] >= cutoff]
        if new_lst:
            rt.subtrecho_times[key] = new_lst
        else:
            rt.subtrecho_times.pop(key, None)


def update_vehicles():

    feed = gtfs_realtime_pb2.FeedMessage()

    try:
        resp = httpx.get(URL_VEHICLE_POSITIONS, timeout=20)
        resp.raise_for_status()
        feed.ParseFromString(resp.content)

    except Exception as e:
        print(f"⚠️ Falha ao baixar/parsing GTFS-RT vehicles: {e}")
        return

    vehicles = {}
    now = int(time.time())

    if not hasattr(rt, "vehicle_subtrecho_state"):
        rt.vehicle_subtrecho_state = {}

    if not hasattr(rt, "subtrecho_times"):
        rt.subtrecho_times = {}

    if not hasattr(rt, "subtrecho_stats"):
        rt.subtrecho_stats = {}

    prune_old_measurements(now)

    for entity in feed.entity:

        if not entity.HasField("vehicle"):
            continue

        veh = entity.vehicle
        desc = veh.vehicle
        pos = veh.position
        trip = veh.trip

        vehicle_id = desc.id or None
        if not vehicle_id:
            continue

        route_id = trip.route_id or None
        trip_id = trip.trip_id or None

        v = {
            "vehicle_id": vehicle_id,
            "vehicle_label": desc.label or None,
            "lat": pos.latitude if pos.HasField("latitude") else None,
            "lon": pos.longitude if pos.HasField("longitude") else None,
            "speed_kmh": parse_speed(pos.speed if pos.HasField("speed") else None),
            "event_ts": veh.timestamp or now,
            "trip_id": trip_id,
            "route_id": route_id,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
            "stop_id": veh.stop_id or None,
            "current_stop_sequence": veh.current_stop_sequence if veh.HasField("current_stop_sequence") else None,
        }

        v["status"] = "on_route" if route_id else "off_route"
        v["shape_id"] = None
        v["shape_pos_m"] = None
        v["shape_len_m"] = None
        v["progress"] = None
        v["speed_avg_kmh"] = None
        v["eta"] = None
        v["heading_deg"] = None

        if route_id:

            key = f"{route_id}_{v['direction_id'] or 0}"
            shape_id = rt.route_shapes.get(key)

            if shape_id and shape_id in rt.shapes:

                pts = rt.shapes[shape_id]
                v["shape_id"] = shape_id

                if v["lat"] and v["lon"]:
                    v["shape_pos_m"] = project_vehicle_shape_position(
                        v["lat"], v["lon"], pts
                    )

                v["shape_len_m"] = compute_shape_length(pts)

                if v["shape_pos_m"] and v["shape_len_m"]:
                    v["progress"] = v["shape_pos_m"] / v["shape_len_m"]

                #
                # 🔥 HEADING GEOMÉTRICO LOCAL (RAIO)
                #
                try:
                    v["heading_deg"] = compute_heading_from_shape(
                        pts,
                        v["shape_pos_m"]
                    )
                except:
                    v["heading_deg"] = None

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
