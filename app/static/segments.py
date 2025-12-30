from app.core.state import RuntimeState
from app.geometry.distance import haversine_m


def build_segments(rt: RuntimeState) -> dict:
    """
    (from_stop, to_stop, route_id, direction_id) -> info
    """
    segments = {}

    for trip_id, stops in rt.stop_times.items():
        trip = rt.trips.get(trip_id)
        if not trip:
            continue

        route_id = trip["route_id"]
        direction_id = trip.get("direction_id", 0)

        for i in range(len(stops) - 1):
            from_stop = stops[i]
            to_stop = stops[i + 1]

            key = (from_stop, to_stop, route_id, direction_id)

            if key not in segments:
                s1 = rt.stops.get(from_stop)
                s2 = rt.stops.get(to_stop)

                if not s1 or not s2:
                    continue

                dist = haversine_m(
                    s1["lat"], s1["lon"],
                    s2["lat"], s2["lon"],
                )

                segments[key] = {
                    "from_stop": from_stop,
                    "to_stop": to_stop,
                    "route_id": route_id,
                    "direction_id": direction_id,
                    "distance_m": dist,
                    "count": 0,
                }

            segments[key]["count"] += 1

    return segments
