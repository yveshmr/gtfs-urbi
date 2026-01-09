import csv
import pickle
from pathlib import Path
from datetime import datetime

from app.config import GTFS_DIR


CACHE_DIR = Path("data/cache/gtfs_parsed")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path():
    return CACHE_DIR / f"routes_{_today_str()}.pkl"


def load_routes():
    """
    Carrega routes.txt (GTFS estático) com cache diário.
    """

    cache_file = _cache_path()

    # --------------------------------------------------
    # 1️⃣ Tenta carregar cache
    # --------------------------------------------------
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    # --------------------------------------------------
    # 2️⃣ Parsing do CSV
    # --------------------------------------------------
    path = GTFS_DIR / "routes.txt"

    routes = {}

    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            routes[row["route_id"]] = row

    # --------------------------------------------------
    # 3️⃣ Salvar cache
    # --------------------------------------------------
    try:
        with open(cache_file, "wb") as f:
            pickle.dump(routes, f)
    except Exception as e:
        print(f"⚠️ Falha ao salvar cache de routes: {e}")

    return routes
