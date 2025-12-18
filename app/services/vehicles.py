import requests
from google.transit import gtfs_realtime_pb2
from datetime import datetime, timezone

from app.core.state import rt
from app.config import URL_VEHICLE_POSITIONS


def update_vehicles():
    # baixa feed protobuf
    raw = requests.get(URL_VEHICLE_POSITIONS).content

    # interpreta protobuf
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)

    vehicles = {}

    # percorre entidades
    for ent in feed.entity:

        if not ent.HasField("vehicle"):
            continue

        v = ent.vehicle

        if not v.HasField("position"):
            continue

        vid = v.vehicle.id or v.vehicle.label or ent.id

        vehicles[vid] = {
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "speed_kmh": float(v.position.speed) if v.position.speed else None,
            "route_id": v.trip.route_id,
            "trip_id": v.trip.trip_id,
            "vehicle_label": v.vehicle.label,
            "event_ts": datetime.fromtimestamp(v.timestamp, tz=timezone.utc).isoformat()
        }

    # atualiza estado global estático
    rt.vehicles.clear()
    rt.vehicles.update(vehicles)

    print(">>> vehicles parsed:", len(rt.vehicles))
