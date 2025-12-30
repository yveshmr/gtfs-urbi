from app.core.state import rt
from app.geometry.distance import haversine_m


def build_shape_stop_index():

    index = {}
    count = 0

    if not rt.trips:
        print("⚠️ shape_stop: trips vazio")
    if not rt.stop_times:
        print("⚠️ shape_stop: stop_times vazio")
    if not rt.shapes:
        print("⚠️ shape_stop: shapes vazio")
    if not rt.stops:
        print("⚠️ shape_stop: stops vazio")

    if not (rt.trips and rt.stop_times and rt.shapes and rt.stops):
        rt.shape_stops = {}
        return

    #
    # trip → shape → stops
    #
    for trip_id, trip in rt.trips.items():

        shape_id = trip.get("shape_id")
        if not shape_id:
            continue

        shape = rt.shapes.get(shape_id)
        if not shape:
            continue

        stops_in_trip = rt.stop_times.get(trip_id)
        if not stops_in_trip:
            continue

        #
        # agora stops_in_trip é lista de stop_ids
        #
        for stop_id in stops_in_trip:

            stop = rt.stops.get(stop_id)
            if not stop:
                continue

            # aceita "stop_lat" / "lat"
            stop_lat = stop.get("stop_lat") or stop.get("lat")
            stop_lon = stop.get("stop_lon") or stop.get("lon")

            if stop_lat is None or stop_lon is None:
                continue

            #
            # encontrar ponto mais próximo no shape
            #
            best_dist = None
            best_shape_m = None

            for lat, lon, dist_m in shape:

                d = haversine_m(stop_lat, stop_lon, lat, lon)

                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_shape_m = dist_m

            #
            # salvar
            #
            index[(shape_id, stop_id)] = best_shape_m
            count += 1

    rt.shape_stops = index
    print(f"✔ shape_stop index built (optimized): {count} entries")
