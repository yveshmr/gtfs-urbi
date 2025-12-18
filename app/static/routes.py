from app.static.loader import download_gtfs_zip, read_csv


def load_routes() -> dict:
    """
    route_id -> {
        short_name,
        long_name,
        type
    }
    """
    zf = download_gtfs_zip()
    df = read_csv(zf, "routes.txt")

    routes = {}

    for _, row in df.iterrows():
        routes[row["route_id"]] = {
            "short_name": row.get("route_short_name"),
            "long_name": row.get("route_long_name"),
            "type": int(row["route_type"]),
        }

    return routes
