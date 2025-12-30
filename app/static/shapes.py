import zipfile
import io
import pandas as pd
import httpx

from app.core.config import URL_GTFS_STATIC_ZIP
from app.geometry.distance import haversine_m
from app.core.state import rt


def load_shapes():
    """
    Lê shapes.txt do ZIP GTFS e popula rt.shapes
    Cada shape vira:
    {
        shape_id: [
            (lat, lon, dist_m_acumulada),
            ...
        ]
    }
    """

    print("⏳ carregando shapes ...")

    resp = httpx.get(URL_GTFS_STATIC_ZIP, timeout=60)
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    df = pd.read_csv(zf.open("shapes.txt"))

    shapes = {}

    grouped = df.groupby("shape_id")

    for sid, g in grouped:

        pts = g.sort_values("shape_pt_sequence")

        acc = 0.0
        out = []

        prev = None

        for _, r in pts.iterrows():
            lat = float(r["shape_pt_lat"])
            lon = float(r["shape_pt_lon"])

            if prev:
                acc += haversine_m(prev[0], prev[1], lat, lon)

            out.append((lat, lon, acc))
            prev = (lat, lon)

        shapes[sid] = out

    rt.shapes = shapes

    print(f"✔ shapes carregados: {len(rt.shapes)}")
