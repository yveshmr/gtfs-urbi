import time
import httpx

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from app.geometry.shape_positioning import project_vehicle_shape_position
from app.services.vehicle_progress import compute_shape_length

from google.transit import gtfs_realtime_pb2


def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None

        return round(speed_raw, 1)

    except:
        return None



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

        #
        # STATUS
        #
        if route_id:
            v["status"] = "on_route"
        else:
            v["status"] = "off_route"

        #
        # SHAPE PROJECTION
        #
        v["shape_id"] = None
        v["shape_pos_m"] = None
        v["shape_len_m"] = None
        v["progress"] = None
        v["speed_avg_kmh"] = None
        v["eta"] = None

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
                # --- SPEED AVERAGE ---
                #
                now_ts = now
                key_hist = v["vehicle_id"]

                if v["status"] == "on_route" and v["shape_pos_m"] is not None:

                    hist = rt.vehicle_history.get(key_hist)

                    if not hist or hist.get("shape_id") != v["shape_id"]:
                        rt.vehicle_history[key_hist] = {
                            "shape_id": v["shape_id"],
                            "first_ts": now_ts,
                            "first_pos": v["shape_pos_m"],
                        }

                    else:
                        dist = max(0.0, v["shape_pos_m"] - hist["first_pos"])
                        dt = max(1, now_ts - hist["first_ts"])
                        v["speed_avg_kmh"] = round((dist / dt) * 3.6, 1)

                #
                # --- ETA ---
                #
                if (
                    v["progress"] is not None
                    and v["speed_avg_kmh"]
                    and v["speed_avg_kmh"] > 3
                ):
                    dist_remaining = max(
                        0.0, v["shape_len_m"] - v["shape_pos_m"]
                    )

                    eta_sec = int(dist_remaining / (v["speed_avg_kmh"] / 3.6))

                    v["eta"] = {
                        "eta_ts": now_ts + eta_sec,
                        "eta_seconds": eta_sec,
                        "dist_remaining_m": round(dist_remaining),
                    }

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
