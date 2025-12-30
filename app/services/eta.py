from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from app.core.config import LOCAL_TZ
from app.core.state import rt


def parse_trip_start(trip):
    """
    trip contém:
      - start_time: "HH:MM:SS"
      - start_date: "YYYYMMDD"
    Retorna datetime timezone aware.
    """
    try:
        t = trip.get("start_time", "")
        d = trip.get("start_date", "")

        if not t or not d:
            return None

        hh, mm, ss = map(int, t.split(":"))
        yyyy = int(d[0:4])
        mm_d = int(d[4:6])
        dd = int(d[6:8])

        dt = datetime(yyyy, mm_d, dd, hh, mm, ss, tzinfo=LOCAL_TZ)
        return dt
    except Exception:
        return None


def compute_eta_seconds(elapsed_seconds: float, progress: float):
    """
    Fórmula:
        eta = elapsed * (1-progress) / progress
    """
    if progress <= 0 or progress >= 1:
        return None

    return elapsed_seconds * (1 - progress) / progress


def estimate_eta_for_vehicle(vehicle: dict):
    """
    Retorna estrutura:
      {
        vehicle_id,
        trip_id,
        route_id,
        progress,
        elapsed_s,
        eta_s,
        eta_ts
      }
    """

    trip_id = vehicle.get("trip_id")
    route_id = vehicle.get("route_id")
    progress = vehicle.get("progress")

    if not trip_id or not route_id:
        return None

    if progress is None:
        return None

    if progress <= 0.01:
        return None

    if progress >= 0.99:
        return {
            "vehicle_id": vehicle["vehicle_id"],
            "trip_id": trip_id,
            "route_id": route_id,
            "progress": progress,
            "eta_s": 0,
            "eta_ts": vehicle["event_ts"],
        }

    # pegar trip no static
    trip = rt.trips.get(trip_id)
    if not trip:
        return None

    start_dt = parse_trip_start(trip)
    if not start_dt:
        return None

    now_dt = datetime.fromtimestamp(vehicle["event_ts"], tz=LOCAL_TZ)

    elapsed_s = (now_dt - start_dt).total_seconds()

    if elapsed_s <= 30:
        return None

    if elapsed_s > 6 * 3600:
        return None

    eta_s = compute_eta_seconds(elapsed_s, progress)

    if eta_s is None:
        return None

    if eta_s > 3 * 3600:
        eta_s = 3 * 3600

    eta_ts = vehicle["event_ts"] + int(eta_s)

    return {
        "vehicle_id": vehicle["vehicle_id"],
        "trip_id": trip_id,
        "route_id": route_id,
        "progress": progress,
        "elapsed_s": int(elapsed_s),
        "eta_s": int(eta_s),
        "eta_ts": int(eta_ts),
    }


def get_all_etas():
    results = []

    for v in rt.vehicles.values():
        r = estimate_eta_for_vehicle(v)
        if r:
            results.append(r)

    return results
