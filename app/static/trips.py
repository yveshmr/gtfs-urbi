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
        trips[row["trip_id"]] = {
            "route_id": row["route_id"],
            "shape_id": row.get("shape_id"),
            "direction_id": row.get("direction_id"),
        }

    return trips
