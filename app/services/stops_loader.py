import csv
from app.config import GTFS_DIR


def load_stops():
    """
    Carrega stops.txt (GTFS estático)
    """
    path = GTFS_DIR / "stops.txt"

    stops = {}

    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            stops[row["stop_id"]] = row

    return stops
