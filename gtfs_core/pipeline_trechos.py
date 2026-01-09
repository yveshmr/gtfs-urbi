# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import List, Tuple

from geopy.distance import geodesic

from app.core.state import rt
from gtfs_core.pairs import PAIRS


@dataclass
class Subtrecho:
    s1: str
    s2: str
    distance_m: float
    group: str
    source: str
    polyline: List[Tuple[float, float]]
    m1: float = 0.0
    m2: float = 0.0
    shape_id: str = ""


# ======================================================
# HELPERS (SEM UNPACK IMPLÍCITO)
# ======================================================
def measure_along_shape(shape_pts, lat, lon):
    best_d = None
    best_m = None

    for p in shape_pts:
        la = p[0]
        lo = p[1]
        m = p[2]

        d = geodesic((la, lo), (lat, lon)).meters
        if best_d is None or d < best_d:
            best_d = d
            best_m = m

    return best_m


# ======================================================
# PIPELINE
# ======================================================
def construir_todos_os_subtrechos() -> List[Subtrecho]:

    print("🧠 Pipeline de subtrechos iniciado (GTFS já carregado)")

    if not rt.shapes or not rt.stops or not rt.stop_times or not rt.trips:
        raise RuntimeError("GTFS não está carregado no runtime")

    # --------------------------------------------------
    # stop_id -> shapes
    # --------------------------------------------------
    stops_to_shapes = {}

    for trip_id, trip in rt.trips.items():
        shape_id = trip.get("shape_id")
        if not shape_id:
            continue

        st_list = rt.stop_times.get(trip_id)
        if not st_list:
            continue

        for st in st_list:
            stop_id = st["stop_id"]
            stops_to_shapes.setdefault(stop_id, set()).add(shape_id)

    subtrechos = []

    # --------------------------------------------------
    # LOOP DOS PARES
    # --------------------------------------------------
    for pair in PAIRS:

        s1 = pair[0]
        s2 = pair[1]

        shapes_s1 = stops_to_shapes.get(s1, set())
        shapes_s2 = stops_to_shapes.get(s2, set())
        candidate_shapes = shapes_s1 & shapes_s2

        if not candidate_shapes:
            continue

        lat1, lon1 = rt.stops[s1]
        lat2, lon2 = rt.stops[s2]

        best = None

        for shape_id in candidate_shapes:

            shape_pts = rt.shapes.get(shape_id)
            if not shape_pts:
                continue

            trip_ids = [
                tid for tid, t in rt.trips.items()
                if t.get("shape_id") == shape_id
            ]
            if not trip_ids:
                continue

            st_list = rt.stop_times.get(trip_ids[0])
            if not st_list:
                continue

            stop_ids = [x["stop_id"] for x in st_list]

            if s1 not in stop_ids or s2 not in stop_ids:
                continue

            i1 = stop_ids.index(s1)
            i2 = stop_ids.index(s2)
            if i2 <= i1:
                continue

            m1 = measure_along_shape(shape_pts, lat1, lon1)
            m2 = measure_along_shape(shape_pts, lat2, lon2)

            if m1 is None or m2 is None or m2 <= m1:
                continue

            dist = m2 - m1

            if best is None or dist < best["dist"]:
                best = {
                    "shape_id": shape_id,
                    "shape_pts": shape_pts,
                    "stop_ids": stop_ids,
                    "m1": m1,
                    "m2": m2,
                    "dist": dist,
                }

        if not best:
            continue

        shape_pts = best["shape_pts"]
        stop_ids = best["stop_ids"]

        i1 = stop_ids.index(s1)
        i2 = stop_ids.index(s2)
        janela = stop_ids[i1:i2 + 1]

        measures = {}
        for sid in janela:
            lat, lon = rt.stops[sid]
            measures[sid] = measure_along_shape(shape_pts, lat, lon)

        # --------------------------------------------------
        # CRIA SUBTRECHOS
        # --------------------------------------------------
        for i in range(len(janela) - 1):
            a = janela[i]
            b = janela[i + 1]

            ma = measures[a]
            mb = measures[b]

            if ma is None or mb is None or mb <= ma:
                continue

            polyline = []
            for p in shape_pts:
                lat = p[0]
                lon = p[1]
                m = p[2]
                if ma <= m <= mb:
                    polyline.append((lat, lon))

            if len(polyline) < 2:
                continue

            subtrechos.append(
                Subtrecho(
                    s1=a,
                    s2=b,
                    distance_m=mb - ma,
                    group=f"{a}->{b}",
                    source="shape",
                    polyline=polyline,
                    m1=ma,
                    m2=mb,
                    shape_id=best["shape_id"],
                )
            )

    print(f"🏁 Pipeline gerou {len(subtrechos)} subtrechos")

    return subtrechos
