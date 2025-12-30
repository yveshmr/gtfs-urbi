import csv
from app.config import GTFS_DIR


def load_trips():
    """
    Carrega trips.txt (GTFS estático)
    """
    path = GTFS_DIR / "trips.txt"

    trips = {}

    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            trips[row["trip_id"]] = row

    return trips
