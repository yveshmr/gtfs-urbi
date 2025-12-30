import time
import httpx
from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS

# protobuf GTFS-RT
from google.transit import gtfs_realtime_pb2

from app.services.vehicle_progress import compute_vehicle_progress


def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None

        # se vier em m/s converte para km/h
        if speed_raw < 60:
            return round(speed_raw * 3.6, 1)

        return round(speed_raw, 1)

    except Exception:
        return None


def update_vehicles():
    """
    Baixa GTFS-RT vehicle-positions e popula rt.vehicles
    Já inclui:
      – shape_id
      – posição no shape (m)
      – comprimento do shape (m)
      – progresso (0–1)
    """

    feed = gtfs_realtime_pb2.FeedMessage()

    try:
        resp = httpx.get(URL_VEHICLE_POSITIONS, timeout=20)
        resp.raise_for_status()

        # protobuf binário
        feed.ParseFromString(resp.content)

    except Exception as e:
        print(f"⚠️ Falha ao baixar/parsing GTFS-RT vehicles: {e}")
        return

    vehicles = {}
    now_ts = int(time.time())

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

            "event_ts": veh.timestamp or now_ts,

            "trip_id": trip_id,
            "route_id": route_id,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,

            "stop_id": veh.stop_id or None,
            "current_stop_sequence": (
                veh.current_stop_sequence if veh.HasField("current_stop_sequence") else None
            ),
        }

        #
        # status
        #
        if route_id:
            v["status"] = "on_route"
        else:
            v["status"] = "off_route"

        #
        # progresso via SHAPE (mesmo sem trip_id)
        #
        prog = compute_vehicle_progress(v)

        v["shape_id"] = prog["shape_id"] if prog else None
        v["shape_pos_m"] = prog["shape_pos_m"] if prog else None
        v["shape_len_m"] = prog["shape_len_m"] if prog else None
        v["progress"] = prog["progress"] if prog else None

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles

    print(f"✔ vehicles updated: {len(vehicles)}")
