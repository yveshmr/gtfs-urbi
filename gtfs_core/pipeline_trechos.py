# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

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
# CONFIGURAÇÃO
# ================================

# Quantos pontos do shape vamos procurar "pra frente" (a partir do i1)
# Isso evita pegar outra ocorrência do stop B muito lá na frente
FORWARD_WINDOW_PTS = 2000

# Guardrail: se um subtrecho consecutivo for maior que isso, provavelmente deu match errado.
# Ajuste conforme sua realidade (às vezes 2500m é bom; às vezes 4000m)
MAX_REASONABLE_SUBTRECHO_M = 2500.0


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
    - Evita shape em "U" buscando B apenas depois de A
    - Limita o range de busca (forward window)
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

        # cache (stop_id, start_i, end_i) -> índice no shape
        stop_index_cache: Dict[Tuple[str, int, int], int] = {}

        # mantém monotonicidade com base no último stop encontrado no shape
        last_i: Optional[int] = None
        last_stop: Optional[str] = None

        for i in range(len(ordered_seqs) - 1):
            s1 = seq_to_stop[ordered_seqs[i]]
            s2 = seq_to_stop[ordered_seqs[i + 1]]

            if s1 not in rt.stops or s2 not in rt.stops:
                last_i = None
                last_stop = None
                continue

            # ---------------- INDICES NO SHAPE ----------------

            # Sempre acha o índice do stop A:
            # - se for sequência contínua, reaproveita last_i
            if last_stop == s1 and last_i is not None:
                i1 = last_i
            else:
                i1 = _nearest_shape_index_between(
                    shape_pts=shape_pts,
                    stop_xy=rt.stops[s1],
                    cache=stop_index_cache,
                    stop_id=s1,
                    start_i=0,
                    end_i=len(shape_pts) - 1
                )

            if i1 is None:
                last_i = None
                last_stop = None
                continue

            # Agora acha stop B procurando APENAS depois de i1, mas dentro de uma janela
            start_i = i1
            end_i = min(len(shape_pts) - 1, i1 + FORWARD_WINDOW_PTS)

            i2 = _nearest_shape_index_between(
                shape_pts=shape_pts,
                stop_xy=rt.stops[s2],
                cache=stop_index_cache,
                stop_id=s2,
                start_i=start_i,
                end_i=end_i
            )

            if i2 is None or i2 <= i1:
                last_i = None
                last_stop = None
                continue

            m1 = shape_pts[i1][2]
            m2 = shape_pts[i2][2]

            if m2 <= m1:
                last_i = None
                last_stop = None
                continue

            dist = m2 - m1

            # Guardrail (evita trechos absurdos em caso de match errado)
            if dist > MAX_REASONABLE_SUBTRECHO_M:
                # se quiser depurar, descomenta esse print
                # print(f"[warn] subtrecho suspeito {s1}->{s2} dist={dist:.1f}m shape={shape_id}")
                last_i = None
                last_stop = None
                continue

            polyline = [
                (lat, lon)
                for (lat, lon, _) in shape_pts[i1:i2 + 1]
            ]

            if len(polyline) < 2:
                last_i = None
                last_stop = None
                continue

            key = (s1, s2)

            # mantém o menor A->B entre todos shapes
            if key not in best or dist < best[key].distance_m:
                best[key] = Subtrecho(
                    s1=s1,
                    s2=s2,
                    distance_m=dist,
                    polyline=polyline
                )

            # atualiza estado pra próxima iteração
            last_i = i2
            last_stop = s2

    print(f"✔ Pipeline ALL finalizado: {len(best)} subtrechos")
    return list(best.values())


# ================================
# UTIL — ÍNDICE MAIS PRÓXIMO (COM RESTRIÇÃO)
# ================================

def _nearest_shape_index_between(
    shape_pts: List[Tuple[float, float, float]],
    stop_xy: Tuple[float, float],
    cache: Dict[Tuple[str, int, int], int],
    stop_id: str,
    start_i: int,
    end_i: int
) -> Optional[int]:
    """
    Retorna o índice do ponto do shape mais próximo do stop,
    MAS procurando somente entre start_i e end_i (inclusive).

    Isso evita escolher um ponto "próximo" errado em shapes que
    passam perto do stop mais de uma vez (loops / retornos).
    """

    if start_i < 0:
        start_i = 0
    if end_i >= len(shape_pts):
        end_i = len(shape_pts) - 1
    if start_i > end_i:
        return None

    cache_key = (stop_id, start_i, end_i)
    if cache_key in cache:
        return cache[cache_key]

    lat, lon = stop_xy

    best_i = None
    best_d = None

    for i in range(start_i, end_i + 1):
        la, lo, _ = shape_pts[i]
        d = (la - lat) ** 2 + (lo - lon) ** 2
        if best_d is None or d < best_d:
            best_d = d
            best_i = i

    if best_i is not None:
        cache[cache_key] = best_i

    return best_i
