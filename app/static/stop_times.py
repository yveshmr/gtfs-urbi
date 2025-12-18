from pathlib import Path
import csv
from collections import defaultdict

from app.config import GTFS_DIR


def load_stop_times() -> dict:
    """
    Retorna:
    trip_id -> lista ordenada de stop_id
    """
    stop_times = defaultdict(list)

    path = GTFS_DIR / "stop_times.txt"

    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_id = row["trip_id"]
            stop_id = row["stop_id"]
            seq = int(row["stop_sequence"])

            stop_times[trip_id].append((seq, stop_id))

    # ordenar por stop_sequence
    result = {}
    for trip_id, items in stop_times.items():
        items.sort(key=lambda x: x[0])
        result[trip_id] = [stop_id for _, stop_id in items]

    return result
