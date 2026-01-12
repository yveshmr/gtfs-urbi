# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.core.state import rt


# ================================
# MODELO
# ================================

@dataclass
class Subtrecho:
    s1: str
    s2: str
    distance_m: float
    polyline: List[Tuple[float, float]]


# ================================
# PIPELINE PRINCIPAL
# ================================

def construir_todos_os_subtrechos() -> List[Subtrecho]:
    """
    Constrói TODOS os subtrechos possíveis A->B
    usando a sequência dos shapes GTFS.

    - Apenas pares consecutivos
    - Se A->B existir em múltiplos shapes, mantém o menor
    - NÃO usa geodesic (somente m acumulado)
    """

    print("🧠 Pipeline ALL — construindo todos os subtrechos possíveis")

    if not rt.shapes or not rt.shape_stop_sequence or not rt.stops:
        raise RuntimeError("GTFS estático não carregado")

    # (s1, s2) -> melhor Subtrecho encontrado
    best: Dict[Tuple[str, str], Subtrecho] = {}

    total_shapes = len(rt.shape_stop_sequence)
    processed = 0

    for shape_id, stop_seq in rt.shape_stop_sequence.items():
        processed += 1

        if shape_id not in rt.shapes:
            continue

        shape_pts = rt.shapes[shape_id]

        if not shape_pts or len(shape_pts) < 2:
            continue

        # ---------------- LOG PROGRESSO ----------------
        if processed % 10 == 0 or processed == total_shapes:
            pct = (processed / total_shapes) * 100
            print(f"⏳ Shapes processados: {processed}/{total_shapes} ({pct:.1f}%)")

        # mapa seq -> stop_id
        seq_to_stop = {seq: sid for sid, seq in stop_seq.items()}
        ordered_seqs = sorted(seq_to_stop.keys())

        # cache stop_id -> índice no shape
        stop_index_cache: Dict[str, int] = {}

        for i in range(len(ordered_seqs) - 1):
            s1 = seq_to_stop[ordered_seqs[i]]
            s2 = seq_to_stop[ordered_seqs[i + 1]]

            if s1 not in rt.stops or s2 not in rt.stops:
                continue

            # ---------------- INDICES NO SHAPE ----------------
            i1 = _nearest_shape_index(shape_pts, rt.stops[s1], stop_index_cache, s1)
            i2 = _nearest_shape_index(shape_pts, rt.stops[s2], stop_index_cache, s2)

            if i1 is None or i2 is None or i1 >= i2:
                continue

            m1 = shape_pts[i1][2]
            m2 = shape_pts[i2][2]

            if m2 <= m1:
                continue

            dist = m2 - m1

            polyline = [
                (lat, lon)
                for (lat, lon, _) in shape_pts[i1:i2 + 1]
            ]

            if len(polyline) < 2:
                continue

            key = (s1, s2)

            if key not in best or dist < best[key].distance_m:
                best[key] = Subtrecho(
                    s1=s1,
                    s2=s2,
                    distance_m=dist,
                    polyline=polyline
                )

    print(f"✔ Pipeline ALL finalizado: {len(best)} subtrechos")
    return list(best.values())


# ================================
# UTIL — ÍNDICE MAIS PRÓXIMO
# ================================

def _nearest_shape_index(
    shape_pts: List[Tuple[float, float, float]],
    stop_xy: Tuple[float, float],
    cache: Dict[str, int],
    stop_id: str
) -> int | None:
    """
    Retorna o índice do ponto do shape mais próximo do stop.
    Usa cache para evitar recomputar.
    """

    if stop_id in cache:
        return cache[stop_id]

    lat, lon = stop_xy

    best_i = None
    best_d = None

    for i, (la, lo, _) in enumerate(shape_pts):
        d = (la - lat) ** 2 + (lo - lon) ** 2  # distância quadrada (rápida)
        if best_d is None or d < best_d:
            best_d = d
            best_i = i

    if best_i is not None:
        cache[stop_id] = best_i

    return best_i
