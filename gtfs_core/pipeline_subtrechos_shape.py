# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import List, Tuple

from geopy.distance import geodesic
from app.core.state import rt
from gtfs_core.pairs import PAIRS


@dataclass
class SubtrechoShape:
    s1: str
    s2: str
    shape_id: str
    distance_m: float
    polyline: List[Tuple[float, float]]
    group: str


def measure_along_shape(shape_pts, lat, lon):
    best_d = None
    best_m = None

    for lat_s, lon_s, m in shape_pts:
        d = geodesic((lat_s, lon_s), (lat, lon)).meters
        if best_d is None or d < best_d:
            best_d = d
            best_m = m

    return best_m


def construir_subtrechos_shape():
    print("🧠 Pipeline SHAPE — construindo subtrechos por pares")

    if not rt.shapes or not rt.stops or not rt.stop_times or not rt.trips:
        raise RuntimeError("GTFS não carregado")

    stops_to_shapes = {}

    for trip_id, trip in rt.trips.items():
        sid = trip.get("shape_id")
        if not sid:
            continue

        for st in rt.stop_times.get(trip_id, []):
            stops_to_shapes.setdefault(st["stop_id"], set()).add(sid)

    out = []

    for s1, s2 in PAIRS:

        shapes = stops_to_shapes.get(s1, set()) & stops_to_shapes.get(s2, set())
        if not shapes:
            continue

        lat1, lon1 = rt.stops[s1]
        lat2, lon2 = rt.stops[s2]

        best = None

        for shape_id in shapes:
            shape_pts = rt.shapes.get(shape_id)
            if not shape_pts:
                continue

            m1 = measure_along_shape(shape_pts, lat1, lon1)
            m2 = measure_along_shape(shape_pts, lat2, lon2)

            if m1 is None or m2 is None or m2 <= m1:
                continue

            dist = m2 - m1

            if best is None or dist < best["dist"]:
                best = {
                    "shape_id": shape_id,
                    "m1": m1,
                    "m2": m2,
                    "dist": dist,
                    "shape_pts": shape_pts,
                }

        if not best:
            continue

        polyline = [
            (lat, lon)
            for lat, lon, m in best["shape_pts"]
            if best["m1"] <= m <= best["m2"]
        ]

        if len(polyline) < 2:
            continue

        out.append(
            SubtrechoShape(
                s1=s1,
                s2=s2,
                shape_id=best["shape_id"],
                distance_m=best["dist"],
                polyline=polyline,
                group=f"{s1}->{s2}",
            )
        )

    print(f"✔ Pipeline SHAPE finalizado: {len(out)} subtrechos")
    return out
