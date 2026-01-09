from app.geometry.distance import haversine_m
from app.core.state import rt


def load_shapes():
    """
    Constrói shapes com distância acumulada A PARTIR dos shapes
    já carregados no runtime (rt.shapes).

    Espera rt.shapes no formato:
        shape_id -> list[ { lat, lon, seq } ]

    Converte para:
        shape_id -> list[ (lat, lon, dist_m_acumulada) ]
    """

    print("⏳ construindo shapes com distância acumulada ...")

    if not getattr(rt, "shapes", None):
        raise RuntimeError("rt.shapes não está carregado")

    shapes_out = {}

    for sid, pts in rt.shapes.items():

        acc = 0.0
        out = []
        prev = None

        for p in pts:
            lat = float(p["lat"])
            lon = float(p["lon"])

            if prev:
                acc += haversine_m(prev[0], prev[1], lat, lon)

            out.append((lat, lon, acc))
            prev = (lat, lon)

        shapes_out[sid] = out

    rt.shapes = shapes_out

    print(f"✔ shapes processados: {len(rt.shapes)}")
