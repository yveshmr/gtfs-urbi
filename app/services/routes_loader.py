import csv
from app.config import GTFS_DIR


def load_routes():
    """
    Carrega routes.txt (GTFS estático)
    """
    path = GTFS_DIR / "routes.txt"

    routes = {}

    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            routes[row["route_id"]] = row

    return routes
