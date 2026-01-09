# -*- coding: utf-8 -*-

"""
Pipeline GTFS → SUBTRECHOS
(Mesma lógica do monolítico — otimizada por SHAPE)

✔ baixa GTFS ZIP diretamente da URL oficial
✔ processa TUDO em memória
✔ percorre apenas shapes que passam pelos dois stops
✔ cria subtrechos entre stops intermediários
✔ preenche geometria (polyline) por metragem acumulada
"""

import io
import zipfile
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd
from geopy.distance import geodesic

from app.core.config import GTFS_STATIC_URL
from gtfs_core.pairs import PAIRS
import requests


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


def load_stops(zf):
    df = pd.read_csv(zf.open("stops.txt"), dtype=str)
    return {
        r["stop_id"]: (float(r["stop_lat"]), float(r["stop_lon"]))
        for _, r in df.iterrows()
    }


def load_stop_times(zf):
    df = pd.read_csv(zf.open("stop_times.txt"), dtype=str)

    trips = {}
    for _, r in df.iterrows():
        tid = r["trip_id"]
        sid = r["stop_id"]
        seq = int(r["stop_sequence"])
        trips.setdefault(tid, []).append((seq, sid))

    out = {}
    for tid, rows in trips.items():
        rows.sort(key=lambda x: x[0])
        out[tid] = [sid for _, sid in rows]

    return out


def load_trips(zf):
    df = pd.read_csv(zf.open("trips.txt"), dtype=str)
    return {r["trip_id"]: r.get("shape_id") for _, r in df.iterrows()}


def load_shapes(zf):
    df = pd.read_csv(zf.open("shapes.txt"), dtype=str)

    rows = {}
    for _, r in df.iterrows():
        sid = r["shape_id"]
        seq = int(r["shape_pt_sequence"])
        lat = float(r["shape_pt_lat"])
        lon = float(r["shape_pt_lon"])
        rows.setdefault(sid, []).append((seq, lat, lon))

    shapes = {}

    for sid, pts in rows.items():
        pts.sort(key=lambda x: x[0])

        lats = [p[1] for p in pts]
        lons = [p[2] for p in pts]

        cum = [0.0]
        for i in range(1, len(pts)):
            a = (lats[i - 1], lons[i - 1])
            b = (lats[i], lons[i])
            cum.append(cum[-1] + geodesic(a, b).meters)

        shapes[sid] = dict(lats=lats, lons=lons, cum=cum)

    return shapes


def measure_along_shape(shape, lat, lon):
    best = None
    best_i = 0
    for i, (la, lo) in enumerate(zip(shape["lats"], shape["lons"])):
        d = geodesic((la, lo), (lat, lon)).meters
        if best is None or d < best:
            best = d
            best_i = i
    return shape["cum"][best_i]


def construir_todos_os_subtrechos() -> List[Subtrecho]:

    print("🌐 Baixando GTFS ZIP para pipeline...")

    resp = requests.get(GTFS_STATIC_URL, timeout=60)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:

        print("📥 Lendo GTFS...")

        stops = load_stops(zf)
        stop_times = load_stop_times(zf)
        trips = load_trips(zf)
        shapes = load_shapes(zf)

        stops_to_shapes = {}

        for tid, sid in trips.items():
            seq = stop_times.get(tid)
            if not seq:
                continue
            for stop in seq:
                stops_to_shapes.setdefault(stop, set()).add(sid)

        subtrechos = []

        for (s1, s2) in PAIRS:

            shapes_s1 = stops_to_shapes.get(s1, set())
            shapes_s2 = stops_to_shapes.get(s2, set())
            candidate_shapes = shapes_s1 & shapes_s2

            if not candidate_shapes:
                continue

            lat1, lon1 = stops[s1]
            lat2, lon2 = stops[s2]

            best_shape = None
            best_dist = None
            best_seq = None
            best_sid = None
            best_m1 = None
            best_m2 = None

            for sid in candidate_shapes:

                tids = [t for t, sh in trips.items() if sh == sid]
                if not tids:
                    continue

                seq = stop_times.get(tids[0])
                if not seq:
                    continue

                if s1 not in seq or s2 not in seq:
                    continue

                i1 = seq.index(s1)
                i2 = seq.index(s2)
                if i2 <= i1:
                    continue

                m1 = measure_along_shape(shapes[sid], lat1, lon1)
                m2 = measure_along_shape(shapes[sid], lat2, lon2)

                if m2 <= m1:
                    continue

                dist = m2 - m1

                if best_dist is None or dist < best_dist:
                    best_shape = shapes[sid]
                    best_dist = dist
                    best_seq = seq
                    best_sid = sid
                    best_m1 = m1
                    best_m2 = m2

            if not best_shape:
                continue

            i1 = best_seq.index(s1)
            i2 = best_seq.index(s2)
            janela = best_seq[i1:i2 + 1]

            measures = {}
            for sid in janela:
                lat, lon = stops[sid]
                measures[sid] = measure_along_shape(best_shape, lat, lon)

            for i in range(len(janela) - 1):
                a = janela[i]
                b = janela[i + 1]

                ma = measures[a]
                mb = measures[b]

                if mb <= ma:
                    continue

                # === GEOMETRIA DO SUBTRECHO (DEFINITIVA) ===
                polyline = [
                    (lat, lon)
                    for lat, lon, m in zip(
                        best_shape["lats"],
                        best_shape["lons"],
                        best_shape["cum"]
                    )
                    if ma <= m <= mb
                ]

                if len(polyline) < 2:
                    continue

                subtrechos.append(
                    Subtrecho(
                        s1=a,
                        s2=b,
                        distance_m=mb - ma,
                        group=f"{s1}->{s2}",
                        source="shape",
                        polyline=polyline,
                        m1=ma,
                        m2=mb,
                        shape_id=best_sid,
                    )
                )

        print(f"🏁 Pipeline gerou {len(subtrechos)} subtrechos")

        return subtrechos
