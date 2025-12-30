from app.core.state import rt


def build_shape_stop_index():
    """
    Cria um índice:
    
    rt.shape_stops[shape_id] = [
        {
            stop_id,
            stop_sequence,
            pos (metros ao longo do shape)
        }
    ]
    """

    index = {}

    for trip_id, stops in rt.stop_times.items():
        trip = rt.trips.get(trip_id)
        if not trip:
            continue

        shape_id = trip.get("shape_id")
        if not shape_id:
            continue

        entries = []

        for st in stops:
            stop_id = st["stop_id"]
            stop = rt.stops.get(stop_id)

            if not stop:
                continue

            pos = stop.get("shape_pos_m")

            # só usamos stops projetados no shape
            if pos is None:
                continue

            entries.append({
                "stop_id": stop_id,
                "stop_sequence": st["stop_sequence"],
                "pos": pos
            })

        if not entries:
            continue

        # ordenar por posição ao longo do shape
        entries.sort(key=lambda x: x["pos"])

        index[shape_id] = entries

    rt.shape_stops = index
    print(f"✔ shape_stop_index criado: {len(index)} shapes")
