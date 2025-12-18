from app.static.loader import download_gtfs_zip, read_csv


def load_trips() -> dict:
    """
    trip_id -> {
        route_id,
        shape_id,
        direction_id,
        trip_headsign
    }
    """

    zf = download_gtfs_zip()
    df = read_csv(zf, "trips.txt")

    trips = {}

    for _, row in df.iterrows():

        trip_id = row["trip_id"]

        # convert direction_id to int or None
        raw_direction = row.get("direction_id")
        if raw_direction not in (None, "", "nan"):
            try:
                direction_id = int(raw_direction)
            except:
                direction_id = None
        else:
            direction_id = None

        trips[trip_id] = {
            "route_id": row["route_id"],
            "shape_id": row.get("shape_id"),
            "direction_id": direction_id,
            "trip_headsign": row.get("trip_headsign"),
        }

    return trips
