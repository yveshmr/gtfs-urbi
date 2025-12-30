from app.static.loader import download_gtfs_zip, read_csv

def load_routes() -> dict:
    zf = download_gtfs_zip()
    df = read_csv(zf, "routes.txt")

    routes = {}

    for _, row in df.iterrows():
        rid = str(row["route_id"]).strip()

        routes[rid] = {
            "route_short_name": str(row["route_short_name"]).strip(),
            "route_long_name":  str(row["route_long_name"]).strip(),
        }

    return routes
