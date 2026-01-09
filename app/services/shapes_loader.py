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
    return CACHE_DIR / f"shapes_{_today_str()}.pkl"


def load_shapes():
    """
    Carrega shapes do GTFS estático com cache diário.

    Retorna:
        dict[
            shape_id -> list[
                {
                    lat,
                    lon,
                    seq
                }
            ]
        ]
    """

    cache_file = _cache_path()

    # --------------------------------------------------
    # 1️⃣ Tenta carregar cache
    # --------------------------------------------------
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                shapes = pickle.load(f)
            return shapes
        except Exception:
            # cache corrompido → refaz
            pass

    # --------------------------------------------------
    # 2️⃣ Parsing do CSV
    # --------------------------------------------------
    path = GTFS_DIR / "shapes.txt"

    shapes = {}

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            sid = row["shape_id"]

            shapes.setdefault(sid, []).append({
                "lat": float(row["shape_pt_lat"]),
                "lon": float(row["shape_pt_lon"]),
                "seq": int(row["shape_pt_sequence"]),
            })

    # ordenar cada shape
    for sid in shapes:
        shapes[sid].sort(key=lambda x: x["seq"])

    # --------------------------------------------------
    # 3️⃣ Salva cache
    # --------------------------------------------------
    try:
        with open(cache_file, "wb") as f:
            pickle.dump(shapes, f)
    except Exception as e:
        print(f"⚠️ Falha ao salvar cache de shapes: {e}")

    return shapes
