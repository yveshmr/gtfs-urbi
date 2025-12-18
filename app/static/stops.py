from app.static.loader import download_gtfs_zip, read_csv


def load_stops() -> dict:
    """
    Retorna um dicionário:
    stop_id -> {name, lat, lon}
    """
    zf = download_gtfs_zip()
    df = read_csv(zf, "stops.txt")

    stops = {}

    for _, row in df.iterrows():
        stops[row["stop_id"]] = {
            "name": row["stop_name"],
            "lat": float(row["stop_lat"]),
            "lon": float(row["stop_lon"]),
        }

    return stops
