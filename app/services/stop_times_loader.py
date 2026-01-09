import csv
import pickle
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from app.core.config import GTFS_DIR
from app.core.state import rt


CACHE_DIR = Path("data/cache/gtfs_parsed")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path():
    return CACHE_DIR / f"stop_times_{_today_str()}.pkl"


def load_stop_times():
    """
    Carrega stop_times.txt do GTFS estático com cache diário.

    Retorna:
        dict: trip_id -> lista ordenada de dicts:
            {
                stop_id,
                stop_sequence,
                arrival_time,
                departure_time
            }

    Também popula:
        rt.shape_stop_sequence:
            shape_id -> { stop_id -> ordem_no_shape }
    """

    cache_file = _cache_path()

    # --------------------------------------------------
    # 1️⃣ Tenta carregar cache
    # --------------------------------------------------
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)

            rt.shape_stop_sequence = data["shape_stop_sequence"]
            return data["stop_times"]

        except Exception:
            # cache corrompido → refaz tudo
            pass

    # --------------------------------------------------
    # 2️⃣ Parsing do CSV (local, já baixado)
    # --------------------------------------------------
    path = GTFS_DIR / "stop_times.txt"

    stop_times = defaultdict(list)

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            trip = row["trip_id"]

            stop_times[trip].append({
                "stop_id": row["stop_id"],
                "stop_sequence": int(row["stop_sequence"]),
                "arrival_time": row["arrival_time"],
                "departure_time": row["departure_time"],
            })

    # ordenar por trip
    for trip_id in stop_times:
        stop_times[trip_id].sort(key=lambda x: x["stop_sequence"])

    # --------------------------------------------------
    # 3️⃣ Construir shape -> stop_sequence
    # --------------------------------------------------
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

            # só grava a primeira ocorrência
            if stop_id not in shape_stop_sequence[shape_id]:
                shape_stop_sequence[shape_id][stop_id] = idx

    rt.shape_stop_sequence = dict(shape_stop_sequence)

    # --------------------------------------------------
    # 4️⃣ Salvar cache
    # --------------------------------------------------
    try:
        with open(cache_file, "wb") as f:
            pickle.dump({
                "stop_times": dict(stop_times),
                "shape_stop_sequence": rt.shape_stop_sequence
            }, f)
    except Exception as e:
        print(f"⚠️ Falha ao salvar cache de stop_times: {e}")

    return dict(stop_times)
