from app.core.state import rt
from app.geometry.distance import haversine


def compute_stop_measures():
    """
    Para cada trip_id, calcula a posição do stop ao longo do shape.
    Armazena em rt.stop_measures[trip_id] = [(stop_id, m), ...]
    """
    result = {}

    for trip_id, stops in rt.stop_times.items():

        shape_id = rt.trips.get(trip_id, {}).get("shape_id")
        if shape_id is None:
            continue

        shape = rt.shapes.get(shape_id)
        if not shape:
            continue

        measures = []
        for sid in stops:

            stop = rt.stops.get(sid)
            if not stop:
                continue

            lat, lon = stop["lat"], stop["lon"]

            # usar função já existente de medição ao longo do shape
            m = shape.measure(lat, lon)  # vamos ajustar isso no próximo passo

            measures.append((sid, m))

        # ordenar
        measures.sort(key=lambda x: x[1])

        result[trip_id] = measures

    rt.stop_measures = result
