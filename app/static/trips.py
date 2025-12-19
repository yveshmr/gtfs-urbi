from app.static.loader import download_gtfs_zip, read_csv


def load_trips() -> dict:
    """
    trip_id -> {
        route_id,
        shape_id,
        direction_id
    }
    """

    zf = download_gtfs_zip()
    df = read_csv(zf, "trips.txt")

    trips = {}

    for _, row in df.iterrows():

        trip_id = str(row["trip_id"]).strip()
        route_id = str(row["route_id"]).strip()

        # direction_id pode ser float, converter para int ou None
        direction = row.get("direction_id")
        if direction == "" or direction is None:
            direction = None
        else:
            direction = int(direction)

        # shape pode ser string ou vazio
        shape = row.get("shape_id")
        if shape == "" or shape is None:
            shape = None
        else:
            shape = str(shape).strip()

        trips[trip_id] = {
            "route_id": route_id,
            "direction_id": direction,
            "shape_id": shape,
        }

    return trips
