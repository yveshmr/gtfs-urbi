from fastapi import APIRouter
from typing import List, Dict

from app.core.state import rt
from gtfs_core.pairs import PAIRS


router = APIRouter(
    prefix="/map/subtrechos",
    tags=["map-subtrechos-pairs"]
)


@router.get("/pairs")
def list_subtrechos_pairs() -> List[Dict]:
    """
    Retorna subtrechos APENAS para os corredores definidos em PAIRS.

    Lógica:
    - Para cada par A1->A2 em PAIRS:
        - encontra a menor rota (shape) que contenha ambos
        - subdivide A1->A2 em subtrechos consecutivos
        - filtra esses subtrechos da base ALL
        - retorna apenas os que possuem estatística
    """

    out = []

    if not hasattr(rt, "subtrechos_all"):
        return out

    if not hasattr(rt, "subtrecho_all_stats"):
        return out

    # =====================================================
    # LOOP DOS CORREDORES OPERACIONAIS
    # =====================================================
    for A1, A2 in PAIRS:

        best = None

        # -------------------------------------------------
        # 1 — Encontrar a MENOR rota válida
        # -------------------------------------------------
        for shape_id, stop_seq in rt.shape_stop_sequence.items():

            if A1 not in stop_seq or A2 not in stop_seq:
                continue

            seq1 = stop_seq[A1]
            seq2 = stop_seq[A2]

            if seq2 <= seq1:
                continue

            # seq -> stop_id
            seq_to_stop = {seq: sid for sid, seq in stop_seq.items()}

            ordered = sorted(
                s for s in seq_to_stop.keys()
                if seq1 <= s <= seq2
            )

            dist = 0.0
            valid = True

            for i in range(len(ordered) - 1):
                sA = seq_to_stop[ordered[i]]
                sB = seq_to_stop[ordered[i + 1]]

                key = (sA, sB)
                st = rt.subtrechos_all.get(key)

                if not st:
                    valid = False
                    break

                dist += st.distance_m

            if not valid:
                continue

            if best is None or dist < best["distance"]:
                best = {
                    "shape_id": shape_id,
                    "ordered_seqs": ordered,
                    "distance": dist,
                    "seq_to_stop": seq_to_stop
                }

        if not best:
            continue

        # -------------------------------------------------
        # 2 — Subdivide em subtrechos reais
        # -------------------------------------------------
        ordered = best["ordered_seqs"]
        seq_to_stop = best["seq_to_stop"]

        for i in range(len(ordered) - 1):
            sA = seq_to_stop[ordered[i]]
            sB = seq_to_stop[ordered[i + 1]]

            key = (sA, sB)

            stats = rt.subtrecho_all_stats.get(key)
            st = rt.subtrechos_all.get(key)

            if not stats or not st or not st.polyline or len(st.polyline) < 2:
                continue

            out.append({
                "pair_id": f"{A1}->{A2}",
                "subtrecho_id": f"{sA}->{sB}",
                "coords": [[lat, lon] for (lat, lon) in st.polyline],
                "speed_kmh": stats["speed_avg_kmh"],
                "n": stats["n"],
                "last_ts": stats["last_ts"],
                "model": "pairs"
            })

    return out
