
# -*- coding: utf-8 -*-
"""
GTFS-RT + GTFS estático (stops/routes/trips/stop_times/shapes) com FastAPI + Leaflet.
Versão: Subsegments + Clustering de Paradas próximas + Média móvel (10min) + Popups persistentes + Highlight
Agora com pré-carregamento: Linhas (route_short_name) por subtrecho e exibição nos popups.
"""

import os
import io
import zipfile
import math
import asyncio
import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, Deque, Set
from collections import deque

import aiohttp
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from geopy.distance import geodesic
from google.transit import gtfs_realtime_pb2
from zoneinfo import ZoneInfo

# =========================
# CONFIGURAÇÃO
# =========================

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

URL_VEHICLE_POSITIONS = os.getenv(
    "URL_VEHICLE_POSITIONS",
    "https://servicos.cittati.com.br/GTFS-RT2/URBI/vehicle-positions",
)
URL_GTFS_STATIC_ZIP = os.getenv(
    "URL_GTFS_STATIC_ZIP",
    "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip",
)

# Pares "grandes" — serão canonicalizados e subdivididos com base no GTFS/shape
PAIRS: List[Tuple[str, str]] = [
    ("113024453", "113025815"),
    ("113025815", "177642723"),
    ("113025815", "113026479"),
    ("113026479", "113021750"),
    ("113021750", "113023740"),
    ("113021750", "113024017"),
    ("113024017", "113023966"),
    ("113021750", "113023830"),

    # Novos pares adicionados
    ("113086903", "113026479"),
    ("113079261", "113024453"),
    ("113077177", "113024460"),
    ("113077178", "113024453"),
    ("424040721", "113024453"),
    ("113264862", "113024453"),
    ("113091599", "113024453"),
    ("113079261", "177642727"),
    ("113077178", "177642727"),
    ("177642723", "113022302"),
    ("113023758", "124898894"),

    # Novos pares solicitados agora
    ("113024604", "113025639"),
    ("113024604", "113024481"),
    ("113079261", "113024484"),
    ("113024604", "113024688"),
    ("113024688", "113024481"),
    ("113024688", "113025641"),
    ("113023761", "113023894"),
    ("113024376", "113024258"),
    ("113023970", "113024465"),
    ("113023834", "113024465"),
    ("113023895", "113024465"),
    ("113023729", "113024465"),
    ("113022301", "113025402"),
    ("113026480", "113077177"),
    ("113026480", "113086903"),
    ("113025812", "113091599"),
    ("113025812", "113024394"),
    ("113025812", "113024325"),
    ("113025812", "113079261"),
    ("113025812", "113077178"),
    ("113025812", "113024471"),
    ("113024482", "113079261"),
    ("113024475", "113024599"),
    ("177527705", "113024626"),

]

# Parâmetros
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "15"))
STATIC_REFRESH_MIN = int(os.getenv("STATIC_REFRESH_MIN", "60"))
RADIUS_FALLBACK_M = float(os.getenv("RADIUS_FALLBACK_M", "50"))
MIN_GAP_SEC = float(os.getenv("MIN_GAP_SEC", "3"))
FRONT_REFRESH_MS = int(os.getenv("FRONT_REFRESH_MS", "5000"))
PORT = int(os.getenv("PORT", "8081"))

# Limites de tempo (10 minutos)
AVG_WINDOW_SEC = int(os.getenv("AVG_WINDOW_SEC", "600"))          # janela para média móvel
STALE_VEHICLE_SEC = int(os.getenv("STALE_VEHICLE_SEC", "600"))    # veículo “fresco”
STALE_PROGRESS_SEC = int(os.getenv("STALE_PROGRESS_SEC", "600"))  # limpar progressos

# Raio de unificação de paradas (padrão 20 m)
MERGE_RADIUS_M = float(os.getenv("MERGE_RADIUS_M", "20"))

# Cores (vermelho/roxo invertidos)
COLOR_PURPLE = "#800080"  # < 5 km/h  (novo: roxo)
COLOR_RED    = "#FF0000"  # 5–10 km/h (novo: vermelho)
COLOR_ORANGE = "#FFA500"  # 10–20
COLOR_GOLD   = "#FFD700"  # 20–30
COLOR_GREEN  = "#00A65A"  # > 30
COLOR_STILL  = "#808080"  # 0 (parado)
COLOR_NODATA = "#000000"  # sem dados

HTTP_HEADERS = {
    # "Authorization": "Bearer <TOKEN>",
    # "x-api-key": "<API_KEY>",
}

# =========================
# UTILITÁRIOS
# =========================

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)

def color_for_speed(kmh: Optional[float]) -> str:
    if kmh is None:
        return COLOR_NODATA
    if kmh == 0:
        return COLOR_STILL
    if kmh < 5:
        return COLOR_PURPLE
    if kmh < 10:
        return COLOR_RED
    if kmh < 20:
        return COLOR_ORANGE
    if kmh <= 30:
        return COLOR_GOLD
    return COLOR_GREEN

def _s(v) -> str:
    try:
        import pandas as pd
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return "" if v is None else str(v)

# =========================
# ESTADO EM MEMÓRIA
# =========================

@dataclass
class VehiclePoint:
    lat: float
    lon: float
    speed_kmh: Optional[float]
    event_ts: dt.datetime
    vehicle_label: Optional[str] = None
    route_short_name: Optional[str] = None

@dataclass
class StaticRoutesTrips:
    route_short_by_route_id: Dict[str, Optional[str]] = field(default_factory=dict)
    route_by_trip_id: Dict[str, Optional[str]] = field(default_factory=dict)
    shape_by_trip_id: Dict[str, Optional[str]] = field(default_factory=dict)

@dataclass
class ShapeData:
    lats: List[float] = field(default_factory=list)
    lons: List[float] = field(default_factory=list)
    cum_m: List[float] = field(default_factory=list)

@dataclass
class StopClusterInfo:
    cluster_id: str
    member_stop_ids: Set[str]
    lat: float
    lon: float
    name: Optional[str] = None

@dataclass
class SegmentState:
    p1: Tuple[float, float]  # centróide s1
    p2: Tuple[float, float]  # centróide s2
    distance_m: float
    last_speed_kmh: Optional[float] = None
    last_vehicle_id: Optional[str] = None
    last_vehicle_label: Optional[str] = None
    last_t_out: Optional[dt.datetime] = None
    progress: Dict[str, dt.datetime] = field(default_factory=dict)  # vehicle_id -> t_in
    polyline: List[Tuple[float, float]] = field(default_factory=list)  # opcional
    source: str = "shape"  # "shape" | "straight"
    group: str = ""        # id lógico do par grande
    # Média móvel
    speed_samples: Deque[Tuple[dt.datetime, float]] = field(default_factory=deque)
    rolling_sum_kmh: float = 0.0
    # Linhas contempladas por este subtrecho (pré-carregadas)
    route_short_names: Set[str] = field(default_factory=set)

@dataclass
class RuntimeState:
    stops: Dict[str, Tuple[float, float, Optional[str]]] = field(default_factory=dict)   # alias -> (lat,lon,name)
    srt: StaticRoutesTrips = field(default_factory=StaticRoutesTrips)
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]] = field(default_factory=dict)   # trip_id -> [(stop_id(alias), seq)]
    shapes: Dict[str, ShapeData] = field(default_factory=dict)
    segments: Dict[Tuple[str, str], SegmentState] = field(default_factory=dict)          # (s1(alias),s2(alias))
    segment_routes: Dict[Tuple[str, str], Set[str]] = field(default_factory=dict)        # (s1,s2) -> {route_short_name}
    vehicles: Dict[str, VehiclePoint] = field(default_factory=dict)                      # vehicle_id -> last point
    stop_alias: Dict[str, str] = field(default_factory=dict)                             # stop_id original -> alias
    clusters: Dict[str, StopClusterInfo] = field(default_factory=dict)                   # alias -> info
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

rt = RuntimeState()

# =========================
# CARGA ESTÁTICA (GTFS)
# =========================

async def fetch_bytes(session: aiohttp.ClientSession, url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=60)
    async with session.get(url, headers=HTTP_HEADERS, timeout=timeout) as resp:
        resp.raise_for_status()
        return await resp.read()

def load_stops_from_zip(zf: zipfile.ZipFile) -> Dict[str, Tuple[float, float, Optional[str]]]:
    import pandas as pd
    name = next((n for n in ("stops.txt", "stops.csv") if n in zf.namelist()), None)
    if not name:
        raise FileNotFoundError("stops.(txt|csv) não encontrado no ZIP.")
    df = pd.read_csv(io.BytesIO(zf.read(name)), dtype=str)
    cols = {c.lower(): c for c in df.columns}
    for n in ("stop_id", "stop_lat", "stop_lon"):
        if n not in cols:
            raise KeyError(f"Coluna obrigatória ausente em stops: {n}")
    sid, slat, slon = cols["stop_id"], cols["stop_lat"], cols["stop_lon"]
    sname = cols.get("stop_name")
    out = {}
    for _, r in df.iterrows():
        stop_id = _s(r[sid]).strip()
        if not stop_id:
            continue
        try:
            lat = float(_s(r[slat]).strip().replace(",", "."))
            lon = float(_s(r[slon]).strip().replace(",", "."))
        except Exception:
            continue
        name = _s(r[sname]).strip() or None if sname else None
        out[stop_id] = (lat, lon, name)
    return out

def load_routes_trips_from_zip(zf: zipfile.ZipFile) -> StaticRoutesTrips:
    import pandas as pd
    srt = StaticRoutesTrips()
    if "routes.txt" in zf.namelist():
        df_routes = pd.read_csv(io.BytesIO(zf.read("routes.txt")), dtype=str)
        cols = {c.lower(): c for c in df_routes.columns}
        if "route_id" in cols and "route_short_name" in cols:
            rid_col, rsn_col = cols["route_id"], cols["route_short_name"]
            for _, r in df_routes[[rid_col, rsn_col]].iterrows():
                rid = _s(r[rid_col]).strip()
                rsn = _s(r[rsn_col]).strip() or None
                if rid:
                    srt.route_short_by_route_id[rid] = rsn
    if "trips.txt" in zf.namelist():
        df_trips = pd.read_csv(io.BytesIO(zf.read("trips.txt")), dtype=str)
        cols = {c.lower(): c for c in df_trips.columns}
        tid_col, rid_col, sid_col = cols.get("trip_id"), cols.get("route_id"), cols.get("shape_id")
        if tid_col:
            for _, r in df_trips.iterrows():
                tid = _s(r[tid_col]).strip()
                if not tid:
                    continue
                if rid_col:
                    rid = _s(r[rid_col]).strip() or None
                    srt.route_by_trip_id[tid] = rid
                if sid_col:
                    sh = _s(r[sid_col]).strip() or None
                    srt.shape_by_trip_id[tid] = sh
    return srt

def load_stop_times_from_zip(zf: zipfile.ZipFile) -> Dict[str, List[Tuple[str, int]]]:
    import pandas as pd
    if "stop_times.txt" not in zf.namelist():
        return {}
    df = pd.read_csv(io.BytesIO(zf.read("stop_times.txt")), dtype=str)
    cols = {c.lower(): c for c in df.columns}
    for n in ("trip_id", "stop_id", "stop_sequence"):
        if n not in cols:
            raise KeyError(f"Coluna obrigatória ausente em stop_times: {n}")
    tid_col, sid_col, seq_col = cols["trip_id"], cols["stop_id"], cols["stop_sequence"]
    out: Dict[str, List[Tuple[str, int]]] = {}
    for _, r in df[[tid_col, sid_col, seq_col]].iterrows():
        tid = _s(r[tid_col]).strip()
        sid = _s(r[sid_col]).strip()
        if not tid or not sid:
            continue
        try:
            seq = int(_s(r[seq_col]).strip())
        except Exception:
            continue
        out.setdefault(tid, []).append((sid, seq))
    for tid in out:
        out[tid].sort(key=lambda x: x[1])
    return out

def load_shapes_from_zip(zf: zipfile.ZipFile) -> Dict[str, ShapeData]:
    import pandas as pd
    if "shapes.txt" not in zf.namelist():
        return {}
    df = pd.read_csv(io.BytesIO(zf.read("shapes.txt")), dtype=str)
    cols = {c.lower(): c for c in df.columns}
    for n in ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"):
        if n not in cols:
            raise KeyError(f"Coluna obrigatória ausente em shapes: {n}")
    id_col, lat_col, lon_col, seq_col = cols["shape_id"], cols["shape_pt_lat"], cols["shape_pt_lon"], cols["shape_pt_sequence"]

    rows: Dict[str, List[Tuple[int, float, float]]] = {}
    for _, r in df[[id_col, lat_col, lon_col, seq_col]].iterrows():
        sh = _s(r[id_col]).strip()
        if not sh:
            continue
        try:
            seq = int(_s(r[seq_col]).strip())
            lat = float(_s(r[lat_col]).strip().replace(",", "."))
            lon = float(_s(r[lon_col]).strip().replace(",", "."))
        except Exception:
            continue
        rows.setdefault(sh, []).append((seq, lat, lon))

    shapes: Dict[str, ShapeData] = {}
    for sh, pts in rows.items():
        pts.sort(key=lambda x: x[0])
        lats = [p[1] for p in pts]
        lons = [p[2] for p in pts]
        cum = [0.0]
        for i in range(1, len(pts)):
            a = (lats[i - 1], lons[i - 1])
            b = (lats[i], lons[i])
            cum.append(cum[-1] + geodesic(a, b).meters)
        shapes[sh] = ShapeData(lats=lats, lons=lons, cum_m=cum)
    return shapes

# --------- Geometria auxiliar ---------

def _meters_per_deg(lat: float) -> Tuple[float, float]:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return m_per_deg_lat, m_per_deg_lon

def _project_point_on_segment_meters(px: float, py: float, x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float]:
    vx, vy = (x1 - x0), (y1 - y0)
    wx, wy = (px - x0), (py - y0)
    denom = vx * vx + vy * vy
    if denom <= 0:
        return 0.0, (wx * wx + wy * wy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    projx = x0 + t * vx
    projy = y0 + t * vy
    dx, dy = (px - projx), (py - projy)
    return t, (dx * dx + dy * dy)

def _measure_along_shape(shape: ShapeData, lat: float, lon: float) -> Tuple[float, int, float, Tuple[float, float]]:
    n = len(shape.lats)
    if n == 0:
        return 0.0, 0, 0.0, (lat, lon)
    if n == 1:
        return 0.0, 0, 0.0, (shape.lats[0], shape.lons[0])

    best_dist2 = float("inf")
    best_i = 0
    best_t = 0.0
    best_proj = (shape.lats[0], shape.lons[0])

    for i in range(n - 1):
        lat0, lon0 = shape.lats[i], shape.lons[i]
        lat1, lon1 = shape.lats[i + 1], shape.lons[i + 1]
        lat_ref = (lat0 + lat1) / 2.0
        mlat, mlon = _meters_per_deg(lat_ref)

        x0, y0 = (lon0 * mlon, lat0 * mlat)
        x1, y1 = (lon1 * mlon, lat1 * mlat)
        px, py = (lon * mlon,  lat * mlat)

        t, d2 = _project_point_on_segment_meters(px, py, x0, y0, x1, y1)
        if d2 < best_dist2:
            best_dist2 = d2
            best_i = i
            best_t = t
            plat = lat0 + (lat1 - lat0) * t
            plon = lon0 + (lon1 - lon0) * t
            best_proj = (plat, plon)

    seg_len = shape.cum_m[best_i + 1] - shape.cum_m[best_i]
    measure_m = shape.cum_m[best_i] + best_t * max(0.0, seg_len)
    return measure_m, best_i, best_t, best_proj

def _interp_point(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

def _extract_polyline_segment(shape: ShapeData, m_start: float, m_end: float) -> List[Tuple[float, float]]:
    if not shape.lats or m_end <= m_start:
        return []
    pts: List[Tuple[float, float]] = []
    n = len(shape.lats)
    for i in range(n - 1):
        a = shape.cum_m[i]
        b = shape.cum_m[i + 1]
        if b < m_start or a > m_end:
            continue
        denom = max(1e-9, (b - a))
        t0 = 0.0 if m_start <= a else (m_start - a) / denom
        t1 = 1.0 if m_end >= b else (m_end - a) / denom
        t0 = max(0.0, min(1.0, t0))
        t1 = max(0.0, min(1.0, t1))
        if t1 < t0:
            continue
        p0 = (shape.lats[i], shape.lons[i])
        p1 = (shape.lats[i + 1], shape.lons[i])
        p1 = (shape.lats[i + 1], shape.lons[i + 1])
        q0 = p0 if t0 <= 0 else _interp_point(p0, p1, t0)
        q1 = p1 if t1 >= 1 else _interp_point(p0, p1, t1)
        if not pts:
            pts.append(q0)
        else:
            if abs(pts[-1][0] - q0[0]) > 1e-12 or abs(pts[-1][1] - q0[1]) > 1e-12:
                pts.append(q0)
        pts.append(q1)
    return pts

# --------- Clusterização (unificação paradas por raio) ---------

def _haversine_m(a, b):
    from math import radians, sin, cos, asin, sqrt
    R = 6371000.0
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*R*asin(sqrt(h))

class UnionFind:
    def __init__(self):
        self.p = {}
        self.r = {}
    def find(self, x):
        if x not in self.p:
            self.p[x] = x
            self.r[x] = 0
            return x
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb: return
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1

def _build_stop_alias_and_clusters(
    stops: Dict[str, Tuple[float, float, Optional[str]]],
    radius_m: float
) -> Tuple[Dict[str, str], Dict[str, StopClusterInfo], Dict[str, Tuple[float,float,Optional[str]]]]:
    if not stops:
        return {}, {}, {}
    lats = [v[0] for v in stops.values()]
    lat_ref = sum(lats) / max(1, len(lats))
    deg_lat = radius_m / 111_320.0
    deg_lon = radius_m / (111_320.0 * max(1e-6, math.cos(math.radians(lat_ref))))

    def key(lat, lon):
        return (int(lat / deg_lat), int(lon / deg_lon))

    buckets: Dict[Tuple[int,int], List[str]] = {}
    uf = UnionFind()

    for sid, (lat, lon, _) in stops.items():
        k = key(lat, lon)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                neigh_key = (k[0] + di, k[1] + dj)
                for other_sid in buckets.get(neigh_key, []):
                    lat2, lon2, _ = stops[other_sid]
                    if _haversine_m((lat, lon), (lat2, lon2)) <= radius_m:
                        uf.union(sid, other_sid)
        buckets.setdefault(k, []).append(sid)

    comp: Dict[str, List[str]] = {}
    for sid in stops.keys():
        root = uf.find(sid)
        comp.setdefault(root, []).append(sid)

    stop_alias: Dict[str, str] = {}
    clusters: Dict[str, StopClusterInfo] = {}
    collapsed_stops: Dict[str, Tuple[float, float, Optional[str]]] = {}

    for root, members in comp.items():
        canonical = min(members)  # determinístico
        lsum = 0.0
        osum = 0.0
        for m in members:
            la, lo, _nm = stops[m]
            lsum += la
            osum += lo
        lat_c = lsum / len(members)
        lon_c = osum / len(members)
        name = stops[canonical][2] if canonical in stops else None

        for m in members:
            stop_alias[m] = canonical

        clusters[canonical] = StopClusterInfo(
            cluster_id=canonical,
            member_stop_ids=set(members),
            lat=lat_c, lon=lon_c, name=name
        )
        collapsed_stops[canonical] = (lat_c, lon_c, name)

    return stop_alias, clusters, collapsed_stops

def _canonicalize_stop_times(
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]],
    stop_alias: Dict[str, str]
) -> Dict[str, List[Tuple[str, int]]]:
    out: Dict[str, List[Tuple[str, int]]] = {}
    for tid, lst in stop_times_by_trip.items():
        new_list: List[Tuple[str, int]] = []
        last_sid = None
        for sid, seq in lst:
            csid = stop_alias.get(sid, sid)
            if csid != last_sid:
                new_list.append((csid, seq))
                last_sid = csid
        out[tid] = new_list
    return out

def _canonicalize_pairs(pairs: List[Tuple[str, str]], stop_alias: Dict[str, str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for s1, s2 in pairs:
        a1 = stop_alias.get(s1, s1)
        a2 = stop_alias.get(s2, s2)
        if a1 != a2:
            out.append((a1, a2))
    out = list(dict.fromkeys(out))
    return out

# --------- Construção de segmentos (subdivisão) ---------

def _compute_best_trip_for_pair(
    s1: str, s2: str,
    stops: Dict[str, Tuple[float, float, Optional[str]]],
    srt: StaticRoutesTrips,
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]],
    shapes: Dict[str, ShapeData],
):
    if s1 not in stops or s2 not in stops:
        return None
    lat1, lon1, _ = stops[s1]
    lat2, lon2, _ = stops[s2]

    best = None
    best_dist = None

    for tid, seqs in stop_times_by_trip.items():
        shape_id = srt.shape_by_trip_id.get(tid)
        if not shape_id:
            continue
        shape = shapes.get(shape_id)
        if not shape or len(shape.lats) < 2:
            continue

        idx1 = next((i for i, (sid, _) in enumerate(seqs) if sid == s1), None)
        if idx1 is None:
            continue
        idx2 = next((i for i, (sid, _) in enumerate(seqs) if sid == s2), None)
        if idx2 is None or idx2 <= idx1:
            continue

        m1, *_ = _measure_along_shape(shape, lat1, lon1)
        m2, *_ = _measure_along_shape(shape, lat2, lon2)
        if m2 <= m1:
            continue
        dist = m2 - m1
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (tid, shape, m1, m2, idx1, idx2)

    return best

def _compute_subsegments_for_pair(
    s1: str, s2: str,
    stops: Dict[str, Tuple[float, float, Optional[str]]],
    srt: StaticRoutesTrips,
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]],
    shapes: Dict[str, ShapeData],
) -> Dict[Tuple[str, str], SegmentState]:
    out: Dict[Tuple[str, str], SegmentState] = {}
    best = _compute_best_trip_for_pair(s1, s2, stops, srt, stop_times_by_trip, shapes)
    if not best:
        return out
    tid, shape, m1, m2, idx1, idx2 = best
    seqs = stop_times_by_trip.get(tid, [])
    if not seqs:
        return out

    window = [sid for (sid, _) in seqs[idx1:idx2+1] if sid in stops]
    if len(window) < 2:
        return out

    measures: Dict[str, float] = {}
    for sid in window:
        lat, lon, _ = stops[sid]
        m, *_ = _measure_along_shape(shape, lat, lon)
        measures[sid] = m

    eps = 1e-3
    for i in range(len(window) - 1):
        a = window[i]
        b = window[i + 1]
        ma = measures[a]
        mb = measures[b]
        if mb <= ma:
            mb = ma + eps

        poly = _extract_polyline_segment(shape, ma, mb)
        lat_a, lon_a, _ = stops[a]
        lat_b, lon_b, _ = stops[b]
        dist_m = max(0.0, mb - ma)
        if not poly:
            poly = [(lat_a, lon_a), (lat_b, lon_b)]
            source = "straight"
            dist_m = geodesic((lat_a, lon_a), (lat_b, lon_b)).meters
        else:
            source = "shape"

        out[(a, b)] = SegmentState(
            p1=(lat_a, lon_a),
            p2=(lat_b, lon_b),
            distance_m=dist_m,
            polyline=poly,
            source=source,
            group=f"{s1}->{s2}",
        )
    return out

def _compute_segments_subdivided(
    pairs: List[Tuple[str, str]],
    stops: Dict[str, Tuple[float, float, Optional[str]]],
    srt: StaticRoutesTrips,
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]],
    shapes: Dict[str, ShapeData],
) -> Dict[Tuple[str, str], SegmentState]:
    segs: Dict[Tuple[str, str], SegmentState] = {}
    for s1, s2 in pairs:
        sub = _compute_subsegments_for_pair(s1, s2, stops, srt, stop_times_by_trip, shapes)
        if sub:
            segs.update(sub)
            continue
        if s1 in stops and s2 in stops:
            lat1, lon1, _ = stops[s1]
            lat2, lon2, _ = stops[s2]
            segs[(s1, s2)] = SegmentState(
                p1=(lat1, lon1),
                p2=(lat2, lon2),
                distance_m=geodesic((lat1, lon1), (lat2, lon2)).meters,
                polyline=[(lat1, lon1), (lat2, lon2)],
                source="straight",
                group=f"{s1}->{s2}",
            )
    return segs

# --------- NOVO: pré-carrega "linhas por subtrecho" ---------
def _build_segment_routes(
    stop_times_by_trip: Dict[str, List[Tuple[str, int]]],
    srt: StaticRoutesTrips
) -> Dict[Tuple[str, str], Set[str]]:
    seg_routes: Dict[Tuple[str, str], Set[str]] = {}
    for tid, seqs in stop_times_by_trip.items():
        if not seqs or len(seqs) < 2:
            continue
        rid = srt.route_by_trip_id.get(tid)
        rsn = srt.route_short_by_route_id.get(rid) if rid else None
        label = (rsn or rid or "").strip()
        if not label:
            # sem route_short_name e sem route_id -> ignora
            continue
        for i in range(len(seqs) - 1):
            s1 = seqs[i][0]
            s2 = seqs[i + 1][0]
            if s1 == s2:
                continue
            seg_routes.setdefault((s1, s2), set()).add(label)
    return seg_routes

async def refresh_static():
    prev_stops, prev_srt = rt.stops, rt.srt
    prev_stoptimes, prev_shapes, prev_segs = rt.stop_times_by_trip, rt.shapes, rt.segments
    prev_alias, prev_clusters, prev_seg_routes = rt.stop_alias, rt.clusters, rt.segment_routes
    try:
        async with aiohttp.ClientSession() as session:
            raw = await fetch_bytes(session, URL_GTFS_STATIC_ZIP)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            stops_raw = load_stops_from_zip(zf)
            srt = load_routes_trips_from_zip(zf)
            try:
                stop_times_by_trip_raw = load_stop_times_from_zip(zf)
            except Exception as e:
                print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] stop_times load error: {e}")
                stop_times_by_trip_raw = {}
            try:
                shapes = load_shapes_from_zip(zf)
            except Exception as e:
                print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] shapes load error: {e}")
                shapes = {}

        stop_alias, clusters, collapsed_stops = _build_stop_alias_and_clusters(stops_raw, MERGE_RADIUS_M)
        stop_times_canon = _canonicalize_stop_times(stop_times_by_trip_raw, stop_alias)
        pairs_canon = _canonicalize_pairs(PAIRS, stop_alias)

        segs = _compute_segments_subdivided(pairs_canon, collapsed_stops, srt, stop_times_canon, shapes)

        # NOVO: constrói mapa (s1,s2) -> {linhas}
        seg_routes = _build_segment_routes(stop_times_canon, srt)

        # injeta "linhas" em cada SegmentState
        for key, seg in segs.items():
            seg.route_short_names = seg_routes.get(key, set())

        async with rt.lock:
            rt.stops = collapsed_stops
            rt.srt = srt
            rt.stop_times_by_trip = stop_times_canon
            rt.shapes = shapes
            rt.segments = segs
            rt.stop_alias = stop_alias
            rt.clusters = clusters
            rt.segment_routes = seg_routes

        print(f"[{dt.datetime.now(LOCAL_TZ)}] [INFO] Static OK: stops={len(collapsed_stops)} trips={len(stop_times_canon)} shapes={len(shapes)} segments={len(segs)} clusters={len(clusters)} seg_routes={len(seg_routes)}")
    except Exception as e:
        print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] Static refresh error: {e}")
        async with rt.lock:
            rt.stops = prev_stops
            rt.srt = prev_srt
            rt.stop_times_by_trip = prev_stoptimes
            rt.shapes = prev_shapes
            rt.segments = prev_segs
            rt.stop_alias = prev_alias
            rt.clusters = prev_clusters
            rt.segment_routes = prev_seg_routes

# =========================
# REALTIME (GTFS-RT)
# =========================

def resolve_route_short_name(trip_id: Optional[str], route_id: Optional[str], srt: StaticRoutesTrips) -> Optional[str]:
    rid = route_id
    if not rid and trip_id:
        rid = srt.route_by_trip_id.get(trip_id)
    if rid:
        return srt.route_short_by_route_id.get(rid)
    return None

def parse_vehicle_positions(raw: bytes, ingestion_ts: dt.datetime) -> List[Dict]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)
    header_ts = dt.datetime.fromtimestamp(feed.header.timestamp, tz=dt.UTC) if getattr(feed.header, "timestamp", None) else None

    rows: List[Dict] = []
    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        vid = (v.vehicle.id or v.vehicle.label or ent.id or "").strip()
        if not vid or not v.HasField("position"):
            continue

        lat = float(v.position.latitude)
        lon = float(v.position.longitude)

        speed_kmh = None
        if getattr(v.position, "speed", None) is not None:
            try:
                # ATENÇÃO: GTFS-RT padrão entrega m/s; se sua fonte entregar km/h, ajuste aqui
                # Mantido conforme seu código original (sem conversão).
                speed_kmh = float(v.position.speed)
            except Exception:
                speed_kmh = None

        stop_id = v.stop_id or None
        provider_ts = dt.datetime.fromtimestamp(getattr(v, "timestamp", 0), tz=dt.UTC) if getattr(v, "timestamp", None) else None
        event_ts = provider_ts or header_ts or ingestion_ts

        rows.append({
            "vehicle_id": vid,
            "vehicle_label": (v.vehicle.label or "").strip() or None,
            "trip_id": v.trip.trip_id or None,
            "route_id": v.trip.route_id or None,
            "latitude": lat,
            "longitude": lon,
            "speed_kmh": speed_kmh,
            "stop_id": stop_id,
            "event_ts": event_ts,
        })
    return rows

# =========================
# MÉDIA MÓVEL POR SUBTRECHO
# =========================

def _prune_segment_samples(seg: SegmentState, now_utc: dt.datetime):
    cutoff = now_utc - dt.timedelta(seconds=AVG_WINDOW_SEC)
    while seg.speed_samples and seg.speed_samples[0][0] < cutoff:
        old_ts, old_speed = seg.speed_samples.popleft()
        seg.rolling_sum_kmh -= old_speed
    n = len(seg.speed_samples)
    seg.last_speed_kmh = (seg.rolling_sum_kmh / n) if n > 0 else None

def _add_speed_sample(seg: SegmentState, ts: dt.datetime, speed_kmh: float):
    seg.speed_samples.append((ts, speed_kmh))
    seg.rolling_sum_kmh += speed_kmh
    _prune_segment_samples(seg, ts)

def update_segments_with_observations(
    observations: List[Dict],
    segments: Dict[Tuple[str, str], SegmentState],
    use_radius_fallback: bool,
):
    for obs in observations:
        vid = obs["vehicle_id"]
        sid_raw = obs.get("stop_id")
        sid = rt.stop_alias.get(sid_raw, sid_raw) if sid_raw else None
        here = (obs["latitude"], obs["longitude"])
        ts = obs["event_ts"]

        for (s1, s2), seg in segments.items():
            got_out = False
            if sid:
                if sid == s1:
                    seg.progress[vid] = ts
                if sid == s2:
                    got_out = True
            elif use_radius_fallback:
                if geodesic(here, seg.p1).meters <= RADIUS_FALLBACK_M:
                    seg.progress[vid] = ts
                if geodesic(here, seg.p2).meters <= RADIUS_FALLBACK_M:
                    got_out = True

            if got_out:
                t_in = seg.progress.get(vid)
                if t_in and (ts - t_in).total_seconds() >= MIN_GAP_SEC:
                    dt_sec = (ts - t_in).total_seconds()
                    speed_kmh = (seg.distance_m / dt_sec) if dt_sec > 0 else None
                    if speed_kmh is not None:
                        _add_speed_sample(seg, ts, speed_kmh)
                    if (seg.last_t_out is None) or (ts > seg.last_t_out):
                        seg.last_vehicle_id = vid
                        try:
                            vp = rt.vehicles.get(vid)
                            seg.last_vehicle_label = vp.vehicle_label if vp else obs.get("vehicle_label")
                        except Exception:
                            seg.last_vehicle_label = obs.get("vehicle_label")
                        seg.last_t_out = ts
                seg.progress.pop(vid, None)

def upsert_vehicles(observations: List[Dict], vehicles: Dict[str, VehiclePoint], srt: StaticRoutesTrips):
    for obs in observations:
        vid = obs["vehicle_id"]
        lat = obs["latitude"]
        lon = obs["longitude"]
        kmh = obs.get("speed_kmh")
        ts = obs["event_ts"]
        vehicle_label = obs.get("vehicle_label")
        rshort = resolve_route_short_name(obs.get("trip_id"), obs.get("route_id"), srt)

        prev = vehicles.get(vid)
        if kmh is None and prev is not None:
            kmh = prev.speed_kmh
        if vehicle_label is None and prev is not None:
            vehicle_label = prev.vehicle_label
        if rshort is None and prev is not None:
            rshort = prev.route_short_name

        vehicles[vid] = VehiclePoint(
            lat=lat, lon=lon, speed_kmh=kmh, event_ts=ts,
            vehicle_label=vehicle_label, route_short_name=rshort
        )

# =========================
# BACKGROUND TASKS
# =========================

def _gc_state(now_utc: dt.datetime):
    # Remove veículos obsoletos
    stale_vids = [vid for vid, vp in rt.vehicles.items()
                  if (now_utc - vp.event_ts).total_seconds() > STALE_VEHICLE_SEC]
    for vid in stale_vids:
        rt.vehicles.pop(vid, None)
    # Remove progressos antigos e atualiza média
    for seg in rt.segments.values():
        old = [vid for vid, t_in in seg.progress.items()
               if (now_utc - t_in).total_seconds() > STALE_PROGRESS_SEC]
        for vid in old:
            seg.progress.pop(vid, None)
        _prune_segment_samples(seg, now_utc)

async def realtime_loop():
    await refresh_static()
    last_static = utcnow()
    # marcador para snapshots de 10 min
    last_snapshot = utcnow()
    async with aiohttp.ClientSession() as session:
        while True:
            tic = utcnow()
            try:
                raw = await fetch_bytes(session, URL_VEHICLE_POSITIONS)
                observations = parse_vehicle_positions(raw, tic)
                async with rt.lock:
                    upsert_vehicles(observations, rt.vehicles, rt.srt)
                    update_segments_with_observations(observations, rt.segments, use_radius_fallback=True)
                    _gc_state(utcnow())
            except Exception as e:
                print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] Realtime error: {e}")

            if (utcnow() - last_static).total_seconds() >= STATIC_REFRESH_MIN * 60:
                try:
                    await refresh_static()
                except Exception as e:
                    print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] Static refresh error: {e}")
                last_static = utcnow()

            # dispara persistência a cada AVG_WINDOW_SEC (10 min)
            try:
                now = utcnow()
                if (now - last_snapshot).total_seconds() >= AVG_WINDOW_SEC:
                    await persist_snapshot_csv(now)  # função adicionada abaixo
                    last_snapshot = now
            except Exception as e:
                print(f"[{dt.datetime.now(LOCAL_TZ)}] [WARN] Snapshot persist error: {e}")

            elapsed = (utcnow() - tic).total_seconds()
            await asyncio.sleep(max(0, POLL_INTERVAL_SEC - elapsed))

# =========================
# API (FASTAPI) + FRONTEND
# =========================

app = FastAPI(title="GTFS RT Live Map — Subsegments", version="2.3")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(realtime_loop())

@app.get("/", response_class=HTMLResponse)
async def index():
    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <title>Mapa GTFS (Subtrechos)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>

  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin="anonymous"
  />

  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
    .leaflet-popup-content {{ font: 14px/1.4 Arial, sans-serif; }}
    .legend {{
      position: absolute;
      bottom: 16px;
      left: 16px;
      z-index: 9999;
      background: rgba(255,255,255,0.9);
      padding: 10px 12px;
      border-radius: 6px;
      box-shadow: 0 0 8px rgba(0,0,0,0.2);
      font-size: 13px;
    }}
    .legend .row {{ margin: 2px 0; }}
    .swatch {{
      display: inline-block; width: 12px; height: 12px; margin-right: 6px;
      vertical-align: middle;
    }}
  </style>
</head>
<body>
  <div id="map"></div>

  <div class="legend">
    <div><b>Velocidade</b></div>
    <div class="row"><span class="swatch" style="background:{COLOR_GREEN}"></span>&gt; 30 km/h</div>
    <div class="row"><span class="swatch" style="background:{COLOR_GOLD}"></span>20–30 km/h</div>
    <div class="row"><span class="swatch" style="background:{COLOR_ORANGE}"></span>10–20 km/h</div>
    <div class="row"><span class="swatch" style="background:{COLOR_RED}"></span>5–10 km/h</div>
    <div class="row"><span class="swatch" style="background:{COLOR_PURPLE}"></span>&lt; 5 km/h</div>
    <div class="row"><span class="swatch" style="background:{COLOR_STILL}"></span>Parado (0 km/h)</div>
    <div class="row"><span class="swatch" style="background:{COLOR_NODATA}"></span>Sem dados</div>
  </div>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin="anonymous"
  ></script>

  <!-- Frontend: inclui Linhas (pré-carregadas) no popup de subtrechos -->
  <script>
    // ======= Parâmetros do front =======
    const REFRESH_MS = {FRONT_REFRESH_MS};
    const DIM_COLOR  = '#CCCCCC';

    // Mapa base
    const map = L.map('map', {{
      center: [-15.793889, -47.882778],
      zoom: 13,
      zoomSnap: 0.25,
      zoomDelta: 0.25
    }});

    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19
    }}).addTo(map);

    // ======= Camadas =======
    const segmentsLayer = L.geoJSON(null, {{
      style: feature => ({{ color: feature.properties.color || '#999', weight: 4, opacity: 0.9 }}),
      onEachFeature: (feature, layer) => {{
        bindSegmentPopup(layer, feature.properties);
        layer.on('click', () => selectSegmentByLayer(layer));
      }}
    }});

    const segmentsLastKnownLayer = L.geoJSON(null, {{
      style: feature => ({{ color: feature.properties.color_last || '#999', weight: 4, opacity: 0.9 }}),
      onEachFeature: (feature, layer) => {{
        bindSegmentLastKnownPopup(layer, feature.properties);
        layer.on('click', () => selectSegmentByLayer(layer));
      }}
    }});

    const vehiclesLayer = L.layerGroup();

    L.control.layers(
      null,
      {{
        "Subtrechos (velocidade média)": segmentsLayer,
        "Subtrechos (Última velocidade conhecida)": segmentsLastKnownLayer,
        "Veículos (tempo real)": vehiclesLayer
      }},
      {{ collapsed: false }}
    ).addTo(map);

    segmentsLayer.addTo(map);
    vehiclesLayer.addTo(map);

    // ======= Estado global =======
    let selectedSegmentKey = null;
    let selectedVehicleId = null;
    const lastKnownBySeg = new Map();

    // ======= Utilitários =======
    function kmhColor(kmh) {{
      if (kmh === null || kmh === undefined) return "{COLOR_NODATA}";
      if (kmh === 0) return "{COLOR_STILL}";
      if (kmh < 5)   return "{COLOR_PURPLE}";
      if (kmh < 10)  return "{COLOR_RED}";
      if (kmh < 20)  return "{COLOR_ORANGE}";
      if (kmh <= 30) return "{COLOR_GOLD}";
      return "{COLOR_GREEN}";
    }}

    const fmtTs = ts => ts ? new Date(ts).toLocaleString('pt-BR') : '—';
    const segmentKey = p => (p.s1 || '') + '|' + (p.s2 || '');

    // ======= Popups =======
    function bindSegmentPopup(layer, p) {{
      const linesList = (p.lines && p.lines.length) ? p.lines.join(', ') : '—';
      const html =
        '<b>Trecho:</b> ' + (p.s1 || '—') + ' → ' + (p.s2 || '—') + '<br/>' +
        '<b>Linhas:</b> ' + linesList + '<br/>' +
        '<b>Velocidade:</b> ' + (p.last_speed_kmh != null ? p.last_speed_kmh.toFixed(1) + ' km/h' : '—') + '<br/>' +
        '<b>Atualizado:</b> ' + fmtTs(p.last_t_out) + '<br/>' +
        '<b>Distância:</b> ' + (p.distance_m != null ? Math.round(p.distance_m) : '—') + ' m<br/>' +
        '<b>Origem:</b> ' + (p.source || '—') + '<br/>' +
        '<b>Grupo:</b> ' + (p.group || '—');
      layer.bindPopup(html, {{ autoPan: true, closeOnClick: false, autoClose: false }});
    }}

    function bindSegmentLastKnownPopup(layer, p) {{
      const linesList = (p.lines && p.lines.length) ? p.lines.join(', ') : '—';
      const html =
        '<b>Trecho:</b> ' + (p.s1 || '—') + ' → ' + (p.s2 || '—') + '<br/>' +
        '<b>Linhas:</b> ' + linesList + '<br/>' +
        '<b>Última velocidade conhecida:</b> ' + (p.last_known_kmh != null ? p.last_known_kmh.toFixed(1) + ' km/h' : '—') + '<br/>' +
        '<b>Última atualização (conhecida):</b> ' + fmtTs(p.last_known_ts) + '<br/>' +
        '<b>Distância:</b> ' + (p.distance_m != null ? Math.round(p.distance_m) : '—') + ' m<br/>' +
        '<b>Origem:</b> ' + (p.source || '—') + '<br/>' +
        '<b>Grupo:</b> ' + (p.group || '—');
      layer.bindPopup(html, {{ autoPan: true, closeOnClick: false, autoClose: false }});
    }}

    function bindVehiclePopup(marker, p) {{
      const html =
        '<b>Velocidade:</b> ' + (p.speed_kmh != null ? p.speed_kmh.toFixed(1) + ' km/h' : '—') + '<br/>' +
        '<b>Prefixo:</b> ' + (p.vehicle_label || '—') + '<br/>' +
        '<b>Linha:</b> ' + (p.route_short_name || '—') + '<br/>' +
        '<b>Atualizado:</b> ' + fmtTs(p.event_ts);
      marker.bindPopup(html, {{ autoPan: true, closeOnClick: false, autoClose: false }});
    }}

    // ======= Seleção =======
    function selectSegmentByLayer(layer) {{
      const p = layer.feature.properties;
      const key = segmentKey(p);
      if (selectedSegmentKey === key) {{
        selectedSegmentKey = null;
        layer.closePopup();
      }} else {{
        selectedSegmentKey = key;
        layer.openPopup();
      }}
      applySegmentHighlight();
    }}

    function selectVehicleByMarker(marker) {{
      const p = marker.options._props;
      const id = p.vehicle_id;
      if (selectedVehicleId === id) {{
        selectedVehicleId = null;
        marker.closePopup();
      }} else {{
        selectedVehicleId = id;
        marker.openPopup();
      }}
      applyVehicleHighlight();
    }}

    // ======= Highlight =======
    function applySegmentHighlight() {{
      const apply = (layer, getBaseColor) => {{
        layer.eachLayer(l => {{
          const p = l.feature?.properties || {{}};
          const key = segmentKey(p);
          const base = getBaseColor(p) || '#999';
          if (selectedSegmentKey) {{
            if (key === selectedSegmentKey) {{
              l.setStyle({{ color: base, weight: 4, opacity: 0.9 }});
            }} else {{
              l.setStyle({{ color: DIM_COLOR, weight: 4, opacity: 0.5 }});
            }}
          }} else {{
            l.setStyle({{ color: base, weight: 4, opacity: 0.9 }});
          }}
        }});
      }};
      apply(segmentsLayer,           p => p.color);
      apply(segmentsLastKnownLayer,  p => p.color_last);
    }}

    function applyVehicleHighlight() {{
      vehiclesLayer.eachLayer(m => {{
        const props = m.options._props || null;
        if (!props) return;
        if (selectedVehicleId) {{
          if (props.vehicle_id === selectedVehicleId) {{
            const c = kmhColor(props.speed_kmh);
            m.setStyle({{ color: c, fillColor: c }});
          }} else {{
            m.setStyle({{ color: DIM_COLOR, fillColor: DIM_COLOR }});
          }}
        }} else {{
          const c = kmhColor(props.speed_kmh);
          m.setStyle({{ color: c, fillColor: c }});
        }}
      }});
    }}

    // ======= Renderização =======
    function renderVehicles(geojson) {{
      vehiclesLayer.clearLayers();
      (geojson.features || []).forEach(f => {{
        const p = f.properties || {{}};
        const g = f.geometry || null;
        if (!g || g.type !== 'Point' || !g.coordinates) return;
        const latlng = [g.coordinates[1], g.coordinates[0]];
        const c = kmhColor(p.speed_kmh);

        const marker = L.circleMarker(latlng, {{
          radius: 4,
          color: c,
          fillColor: c,
          fillOpacity: 1.0,
          weight: 1
        }});
        marker.options._props = p;
        bindVehiclePopup(marker, p);
        marker.on('click', () => selectVehicleByMarker(marker));
        vehiclesLayer.addLayer(marker);
      }});

      if (selectedVehicleId) {{
        let reopened = false;
        vehiclesLayer.eachLayer(m => {{
          const props = m.options._props || null;
          if (props && props.vehicle_id === selectedVehicleId) {{
            applyVehicleHighlight();
            m.openPopup();
            reopened = true;
          }}
        }});
        if (!reopened) {{
          selectedVehicleId = null;
          applyVehicleHighlight();
        }}
      }} else {{
        applyVehicleHighlight();
      }}
    }}

    function renderSegments(geojson) {{
      segmentsLayer.clearLayers();
      segmentsLayer.addData(geojson);

      const feats = geojson.features || [];
      feats.forEach(f => {{
        const p = f.properties || {{}};
        const key = segmentKey(p);
        if (p.last_speed_kmh != null) {{
          lastKnownBySeg.set(key, {{ kmh: p.last_speed_kmh, tsIso: p.last_t_out || null, lines: p.lines || [] }});
        }} else {{
          // mantém cache existente sem sobrescrever linhas
          const prev = lastKnownBySeg.get(key);
          if (prev && (!prev.lines || prev.lines.length === 0) && p.lines && p.lines.length) {{
            prev.lines = p.lines;
          }}
        }}
      }});

      const lastKnownFeatures = feats
        .map(f => {{
          const p = f.properties || {{}};
          const key = segmentKey(p);
          const lk = lastKnownBySeg.get(key);
          if (!lk) return null;
          const color_last = kmhColor(lk.kmh);
          const props = {{
            s1: p.s1, s2: p.s2,
            distance_m: p.distance_m,
            source: p.source,
            group: p.group,
            last_known_kmh: lk.kmh,
            last_known_ts: lk.tsIso,
            color_last,
            lines: p.lines || lk.lines || []
          }};
          return {{
            type: 'Feature',
            geometry: f.geometry,
            properties: props
          }};
        }})
        .filter(Boolean);

      const fcLast = {{ type: 'FeatureCollection', features: lastKnownFeatures }};
      segmentsLastKnownLayer.clearLayers();
      segmentsLastKnownLayer.addData(fcLast);

      applySegmentHighlight();
      if (selectedSegmentKey) {{
        let reopened = false;

        const tryReopen = (layer, bindFn) => {{
          layer.eachLayer(l => {{
            if (reopened) return;
            const p = l.feature?.properties || {{}};
            if (segmentKey(p) === selectedSegmentKey) {{
              bindFn(l, p);
              l.openPopup();
              reopened = true;
            }}
          }});
        }};

        if (map.hasLayer(segmentsLayer)) {{
          tryReopen(segmentsLayer, bindSegmentPopup);
        }}
        if (!reopened && map.hasLayer(segmentsLastKnownLayer)) {{
          tryReopen(segmentsLastKnownLayer, bindSegmentLastKnownPopup);
        }}

        if (!reopened) {{
          selectedSegmentKey = null;
          applySegmentHighlight();
        }}
      }}
    }}

    // ======= Ciclo de atualização =======
    async function fetchJSON(url) {{
      const resp = await fetch(url, {{ cache: 'no-cache' }});
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return await resp.json();
    }}

    async function refreshData() {{
      try {{
        const [seg, veh] = await Promise.all([
          fetchJSON('/geo/segments'),
          fetchJSON('/geo/vehicles')
        ]);
        renderSegments(seg);
        renderVehicles(veh);

        if (!window.__fitOnce && seg.features && seg.features.length) {{
          const bounds = L.geoJSON(seg).getBounds();
          if (bounds.isValid()) {{
            map.fitBounds(bounds.pad(0.1));
            window.__fitOnce = true;
          }}
        }}
      }} catch (e) {{
        console.warn('Falha ao atualizar dados:', e);
      }}
    }}

    // Inicializa
    refreshData();
    setInterval(refreshData, REFRESH_MS);
  </script>
</body>
</html>
    """
    return HTMLResponse(html)

@app.get("/geo/vehicles", response_class=JSONResponse)
async def geo_vehicles():
    async with rt.lock:
        feats = []
        for vid, vp in rt.vehicles.items():
            props = {
                "vehicle_id": vid,
                "speed_kmh": vp.speed_kmh,
                "vehicle_label": vp.vehicle_label,
                "route_short_name": vp.route_short_name,
                "event_ts": vp.event_ts.astimezone(dt.UTC).isoformat()
            }
            feat = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [vp.lon, vp.lat]},
                "properties": props
            }
            feats.append(feat)
        return JSONResponse({"type": "FeatureCollection", "features": feats})

@app.get("/geo/segments", response_class=JSONResponse)
async def geo_segments():
    async with rt.lock:
        feats = []
        for (s1, s2), seg in rt.segments.items():
            props = {
                "s1": s1, "s2": s2,
                "distance_m": seg.distance_m,
                "last_speed_kmh": seg.last_speed_kmh,
                "last_vehicle_id": seg.last_vehicle_id,
                "last_vehicle_label": seg.last_vehicle_label,
                "last_t_out": seg.last_t_out.astimezone(dt.UTC).isoformat() if seg.last_t_out else None,
                "color": color_for_speed(seg.last_speed_kmh),
                "source": seg.source,
                "group": seg.group,
                # NOVO: lista de linhas pré-carregadas (ordenada)
                "lines": sorted(list(seg.route_short_names)) if seg.route_short_names else []
            }
            if seg.polyline and len(seg.polyline) >= 2:
                coords = [[lon, lat] for (lat, lon) in seg.polyline]
            else:
                coords = [[seg.p1[1], seg.p1[0]], [seg.p2[1], seg.p2[0]]]
            feat = {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": props
            }
            feats.append(feat)
        return JSONResponse({"type": "FeatureCollection", "features": feats})

@app.get("/health", response_class=JSONResponse)
async def health():
    async with rt.lock:
        now = utcnow()
        fresh = sum(1 for v in rt.vehicles.values()
                    if (now - v.event_ts).total_seconds() <= STALE_VEHICLE_SEC)
        seg_shape = sum(1 for s in rt.segments.values() if s.source == "shape")
        seg_straight = sum(1 for s in rt.segments.values() if s.source == "straight")
        return JSONResponse({
            "status": "ok",
            "vehicles_total": len(rt.vehicles),
            "vehicles_fresh": fresh,
            "segments": len(rt.segments),
            "segments_by_origin": {"shape": seg_shape, "straight": seg_straight},
            "clusters": len(rt.clusters),
            "server_time_utc": now.isoformat(),
        })

# =========================
# SNAPSHOT (CSV novo a cada 10 min) — ADIÇÃO SOLICITADA
# =========================

import csv

def _compute_window_avgs_from_existing(seg: SegmentState, now_utc: dt.datetime) -> Tuple[Optional[float], Optional[float], int]:
    """
    Calcula:
      - média de velocidade (km/h) dos últimos 10 min
      - média de tempo (s) reconstruído por travessia (distance / speed)
      - n_samples na janela

    Usa seg.speed_samples + seg.rolling_sum_kmh. Poda a janela com _prune_segment_samples.
    """
    _prune_segment_samples(seg, now_utc)

    n = len(seg.speed_samples)
    avg_kmh = (seg.rolling_sum_kmh / n) if n > 0 else None

    if n > 0 and seg.distance_m > 0:
        dt_list = []
        for ts, kmh in seg.speed_samples:
            if kmh is None or kmh <= 0:
                continue
            mps = kmh * (1000.0 / 3600.0)  # km/h -> m/s
            dt_sec = seg.distance_m / mps
            dt_list.append(dt_sec)
        avg_sec = (sum(dt_list) / len(dt_list)) if dt_list else None
    else:
        avg_sec = None

    return avg_kmh, avg_sec, n


async def persist_snapshot_csv(now_utc: dt.datetime, out_dir: str = "snapshots"):
    """
    Gera um CSV novo a cada snapshot, com agregados de 10 min por subtrecho:
    Nome do arquivo inclui timestamp completo para evitar sobrescrita.
    Exemplo: snapshots/segments_20251123_144100.csv
    """
    os.makedirs(out_dir, exist_ok=True)

    # Nome único por snapshot (data + hora)
    fname = f"segments_{now_utc.strftime('%Y%m%d_%H%M%S')}.csv"
    path = os.path.join(out_dir, fname)

    # Monta linhas sob lock
    rows = []
    async with rt.lock:
        for (s1, s2), seg in rt.segments.items():
            avg_kmh, avg_sec, n = _compute_window_avgs_from_existing(seg, now_utc)
            if n <= 0:
                continue
            lines = sorted(list(seg.route_short_names)) if seg.route_short_names else []
            rows.append({
                "ts_utc": now_utc.astimezone(dt.UTC).isoformat(),
                "s1": s1,
                "s2": s2,
                "group": seg.group,
                "source": seg.source,
                "distance_m": f"{seg.distance_m:.3f}",
                "avg_kmh_10m": f"{avg_kmh:.3f}" if avg_kmh is not None else "",
                "avg_sec_10m": f"{avg_sec:.3f}" if avg_sec is not None else "",
                "n_samples": str(n),
                "lines": ", ".join(lines)
            })

    # Escreve arquivo novo (modo "w") com cabeçalho
    fieldnames = ["ts_utc","s1","s2","group","source","distance_m","avg_kmh_10m","avg_sec_10m","n_samples","lines"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[{dt.datetime.now(LOCAL_TZ)}] [INFO] Snapshot CSV criado: {path} ({len(rows)} linhas)")

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)

