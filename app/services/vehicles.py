import time
import httpx

from app.core.state import rt
from app.core.config import URL_VEHICLE_POSITIONS
from app.geometry.shape_positioning import project_vehicle_shape_position
from app.services.vehicle_progress import compute_shape_length
from app.services.realtime_subtrechos import find_subtrecho_for_position

from google.transit import gtfs_realtime_pb2


AVG_WINDOW_SEC = 900  # 10 min


def parse_speed(speed_raw):
    try:
        if speed_raw is None:
            return None
        return round(speed_raw, 1)
    except:
        return None


def prune_old_measurements(now_ts: int):
    """
    Mantém apenas medições ainda dentro da janela móvel
    """
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

    #
    # LIMPA MEDIÇÕES ANTIGAS
    #
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
                # SUBTRECHOS
                #
                try:
                    current = rt.vehicle_subtrecho_state.get(vehicle_id)
                    detected = None

                    if v["shape_id"] and v["shape_pos_m"] is not None:
                        detected = find_subtrecho_for_position(
                            v["shape_id"],
                            v["shape_pos_m"]
                        )

                    #
                    # entrou
                    #
                    if detected and (not current or current.get("subtrecho") != detected):

                        rt.vehicle_subtrecho_state[vehicle_id] = {
                            "subtrecho": detected,
                            "entered_at": now
                        }

                        print(
                            f"🚍 veículo {vehicle_id} entrou em "
                            f"{detected.s1}->{detected.s2} "
                            f"(shape {detected.shape_id})"
                        )

                    #
                    # saiu
                    #
                    if current and not detected:

                        st = current["subtrecho"]
                        start_ts = current["entered_at"]
                        end_ts = now
                        duration = max(1, end_ts - start_ts)

                        #
                        # --- OUTLIERS ---
                        #
                        if duration < 5:
                            continue

                        if duration > 1800:
                            continue

                        key_triplet = (st.shape_id, st.s1, st.s2)

                        rt.subtrecho_times.setdefault(key_triplet, []).append({
                            "vehicle_id": vehicle_id,
                            "start_ts": start_ts,
                            "end_ts": end_ts,
                            "duration_s": duration,
                        })

                        print(
                            f"🏁 veículo {vehicle_id} saiu de "
                            f"{st.s1}->{st.s2} "
                            f"(shape {st.shape_id}) "
                            f"({duration}s)"
                        )

                        #
                        # AGGREGAÇÃO — SÓ SE HOUVER MEDIÇÕES RECENTES
                        #
                        cutoff = now - AVG_WINDOW_SEC

                        recent = [
                            m for m in rt.subtrecho_times[key_triplet]
                            if m["end_ts"] >= cutoff
                        ]

                        if recent:
                            avg = sum(m["duration_s"] for m in recent) / len(recent)

                            rt.subtrecho_stats[key_triplet] = {
                                "window_start": min(m["end_ts"] for m in recent),
                                "window_end": max(m["end_ts"] for m in recent),
                                "n": len(recent),
                                "avg_s": round(avg, 1),
                            }
                        else:
                            rt.subtrecho_stats.pop(key_triplet, None)

                        rt.vehicle_subtrecho_state.pop(vehicle_id, None)

                except Exception as e:
                    print(f"⚠️ erro realtime subtrecho: {e}")

        vehicles[vehicle_id] = v

    rt.vehicles = vehicles
    print(f"✔ vehicles updated: {len(vehicles)}")
