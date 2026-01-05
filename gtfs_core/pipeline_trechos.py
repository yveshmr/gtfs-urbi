# -*- coding: utf-8 -*-

"""
Pipeline de criação de SUBTRECHOS baseado no código monolítico.
"""

import io
import zipfile
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd
from geopy.distance import geodesic

from .pairs import PAIRS


@dataclass
class Subtrecho:
    s1: str
    s2: str
    distance_m: float
    group: str
    source: str
    polyline: List[Tuple[float, float]]


def load_stops(zf: zipfile.ZipFile):
    df = pd.read_csv(io.BytesIO(zf.read("stops.txt")), dtype=str)
    out = {}
    for _, r in df.iterrows():
        sid = r["stop_id"].strip()
        lat = float(str(r["stop_lat"]).replace(",", "."))
        lon = float(str(r["stop_lon"]).replace(",", "."))
        out[sid] = (lat, lon)
    return out


def load_stop_times(zf: zipfile.ZipFile):
    df = pd.read_csv(io.BytesIO(zf.read("stop_times.txt")), dtype=str)
    trips = {}
    for _, r in df.iterrows():
        tid = r["trip_id"]
        sid = r["stop_id"]
        seq = int(r["stop_sequence"])
        trips.setdefault(tid, []).append((sid, seq))
    for tid in trips:
        trips[tid].sort(key=lambda x: x[1])
    return trips


def load_trips(zf: zipfile.ZipFile):
    df = pd.read_csv(io.BytesIO(zf.read("trips.txt")), dtype=str)
    out = {}
    for _, r in df.iterrows():
        out[r["trip_id"]] = r.get("shape_id")
    return out


def load_shapes(zf: zipfile.ZipFile):
    if "shapes.txt" not in zf.namelist():
        return {}

    df = pd.read_csv(io.BytesIO(zf.read("shapes.txt")), dtype=str)

    rows = {}
    for _, r in df.iterrows():
        sid = r["shape_id"]
        seq = int(r["shape_pt_sequence"])
        lat = float(str(r["shape_pt_lat"]).replace(",", "."))
        lon = float(str(r["shape_pt_lon"]).replace(",", "."))
        rows.setdefault(sid, []).append((seq, lat, lon))

    shapes = {}
    for sid, pts in rows.items():
        pts.sort(key=lambda x: x[0])
        lats = [p[1] for p in pts]
        lons = [p[2] for p in pts]
        cum = [0.0]
        for i in range(1, len(pts)):
            a = (lats[i-1], lons[i-1])
            b = (lats[i], lons[i])
            cum.append(cum[-1] + geodesic(a, b).meters)
        shapes[sid] = {"lats": lats, "lons": lons, "cum": cum}
    return shapes


def measure_along_shape(shape, lat, lon):
    best = None
    best_i = 0
    for i in range(len(shape["lats"]) - 1):
        a = (shape["lats"][i], shape["lons"][i])
        d = geodesic(a, (lat, lon)).meters
        if best is None or d < best:
            best = d
            best_i = i
    return shape["cum"][best_i]


def construir_todos_os_subtrechos(gtfs_zip_bytes: bytes) -> List[Subtrecho]:

    with zipfile.ZipFile(io.BytesIO(gtfs_zip_bytes)) as zf:

        stops = load_stops(zf)
        stop_times = load_stop_times(zf)
        trips = load_trips(zf)
        shapes = load_shapes(zf)

        subtrechos = []

        for s1, s2 in PAIRS:

            best = None
            best_dist = None

            for tid, seqs in stop_times.items():

                ids = [x[0] for x in seqs]
                if s1 not in ids or s2 not in ids:
                    continue

                i1 = ids.index(s1)
                i2 = ids.index(s2)

                if i2 <= i1:
                    continue

                shape_id = trips.get(tid)
                shape = shapes.get(shape_id)
                if not shape:
                    continue

                m1 = measure_along_shape(shape, *stops[s1])
                m2 = measure_along_shape(shape, *stops[s2])

                if m2 <= m1:
                    continue

                dist = m2 - m1

                if best_dist is None or dist < best_dist:
                    best = (seqs, shape, m1, m2)
                    best_dist = dist

            if not best:
                continue

            seqs, shape, m1, m2 = best

            ids = [x[0] for x in seqs]
            window = ids[ids.index(s1):ids.index(s2)+1]

            measures = {
                sid: measure_along_shape(shape, *stops[sid])
                for sid in window
            }

            for i in range(len(window) - 1):

                a = window[i]
                b = window[i+1]
                ma = measures[a]
                mb = measures[b]

                if mb <= ma:
                    continue

                dist_m = mb - ma

                subtrechos.append(
                    Subtrecho(
                        s1=a,
                        s2=b,
                        distance_m=dist_m,
                        group=f"{s1}->{s2}",
                        source="shape",
                        polyline=[]
                    )
                )

        return subtrechos
