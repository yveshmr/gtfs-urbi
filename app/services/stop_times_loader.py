import csv
import io
import zipfile
import httpx
from collections import defaultdict

from app.core.config import URL_GTFS_STATIC_ZIP
from app.core.state import rt


def load_stop_times():
    """
    Carrega stop_times.txt direto do ZIP GTFS.

    Retorna:
        dict: trip_id -> lista ordenada de dicts:
            {
                stop_id,
                stop_sequence,
                arrival_time,
                departure_time
            }

    E constrói também:
        rt.shape_stop_sequence:
            shape_id -> { stop_id -> ordem_no_shape }
    """

    resp = httpx.get(URL_GTFS_STATIC_ZIP, timeout=60)
    resp.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(resp.content))

    with z.open("stop_times.txt") as f:
        rows = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

        stop_times = defaultdict(list)

        for row in rows:
            trip = row["trip_id"]

            stop_times[trip].append({
                "stop_id": row["stop_id"],
                "stop_sequence": int(row["stop_sequence"]),
                "arrival_time": row["arrival_time"],
                "departure_time": row["departure_time"],
            })

    # garantir ordenação por trip
    for trip_id in stop_times:
        stop_times[trip_id].sort(key=lambda x: x["stop_sequence"])

    # =====================================================
    # NOVO: construir índice shape -> stop_sequence
    # =====================================================

    shape_stop_sequence = defaultdict(dict)

    for trip_id, stops in stop_times.items():

        trip = rt.trips.get(trip_id)
        if not trip:
            continue

        shape_id = trip.get("shape_id")
        if not shape_id:
            continue

        for idx, st in enumerate(stops):
            stop_id = st["stop_id"]

            # só grava a PRIMEIRA ocorrência no shape
            if stop_id not in shape_stop_sequence[shape_id]:
                shape_stop_sequence[shape_id][stop_id] = idx

    # expõe no runtime
    rt.shape_stop_sequence = dict(shape_stop_sequence)

    return dict(stop_times)
