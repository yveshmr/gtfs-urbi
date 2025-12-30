import csv
import io
import zipfile
import httpx
from app.core.config import URL_GTFS_STATIC_ZIP


def load_stop_times():
    """
    Carrega stop_times.txt direto do ZIP GTFS.
    Retorna dict: trip_id -> lista ordenada de stops
    """

    resp = httpx.get(URL_GTFS_STATIC_ZIP, timeout=60)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))

    with z.open("stop_times.txt") as f:
        rows = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

        stop_times = {}

        for row in rows:
            trip = row["trip_id"]

            stop_times.setdefault(trip, []).append({
                "stop_id": row["stop_id"],
                "stop_sequence": int(row["stop_sequence"]),
                "arrival_time": row["arrival_time"],
                "departure_time": row["departure_time"],
            })

        # garantir ordenação
        for t in stop_times:
            stop_times[t].sort(key=lambda x: x["stop_sequence"])

        return stop_times
