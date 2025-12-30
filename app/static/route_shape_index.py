from app.core.state import rt

def build_route_shape_index():
    """
    Creates a mapping:
        (route_id, direction_id) → shape_id
    """

    index = {}

    for trip_id, t in rt.trips.items():
        route_id = t.get("route_id")
        shape_id = t.get("shape_id")
        direction_id = t.get("direction_id")

        if not route_id or not shape_id:
            continue

        key = (route_id, direction_id)

        if key not in index:
            index[key] = shape_id

    rt.route_shapes = index
    print(f"✔ route_shapes index built: {len(index)} entries")
