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

    # Abre o arquivo GTFS estático
    zf = download_gtfs_zip()
    df = read_csv(zf, "trips.txt")

    trips = {}

    for _, row in df.iterrows():

        trip_id = row["trip_id"]

        trips[trip_id] = {
            "route_id": row["route_id"],
            "shape_id": row.get("shape_id"),
            "direction_id": (
                int(row["direction_id"])
                if not pd.isna(row.get("direction_id"))
                else None
            ),
            "trip_headsign": row.get("trip_headsign"),
        }

    return trips
