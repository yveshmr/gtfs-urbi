import csv
from app.config import GTFS_DIR


def load_shapes():
    """
    Carrega shapes.txt do GTFS estático
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

    return shapes
