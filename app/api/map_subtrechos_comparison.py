from fastapi import APIRouter
from typing import List

from app.core.state import rt

router = APIRouter(
    prefix="/map/subtrechos/comparison",
    tags=["map"],
)


@router.get("")
def map_subtrechos_comparison():
    """
    Retorna subtrechos ALL com comparação histórico × realtime.

    - Somente leitura
    - Não recalcula nada
    - Usa rt.subtrecho_all_stats
    - Geometria vem do ALL (polyline do shape), não linha reta stop->stop
    """

    features: List[dict] = []

    if not hasattr(rt, "subtrecho_all_stats"):
        return {
            "type": "FeatureCollection",
            "features": [],
        }

    for (s1, s2), stats in rt.subtrecho_all_stats.items():

        comparison = stats.get("comparison")
        if not comparison:
            # sem histórico → não entra na camada
            continue

        st = rt.subtrechos_all.get((s1, s2))
        if not st:
            continue

        # ✅ geometria seguindo shape (polyline canônica do ALL)
        if not getattr(st, "polyline", None) or len(st.polyline) < 2:
            continue

        coords = [[lon, lat] for (lat, lon) in st.polyline]

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "s1": s1,
                "s2": s2,

                # realtime
                "speed_realtime_kmh": stats.get("speed_avg_kmh"),
                "n_realtime": stats.get("n"),
                "last_ts": stats.get("last_ts"),

                # histórico
                "speed_hist_kmh": comparison["historical"]["avg_speed_kmh"],
                "time_hist_sec": comparison["historical"]["avg_time_sec"],
                "n_hist": comparison["historical"]["n_samples"],
                "confidence": comparison["historical"]["confidence"],

                # comparação
                "ratio": comparison["comparison"]["ratio"],
                "delta_speed_kmh": comparison["comparison"]["delta_speed_kmh"],
                "delta_time_sec": comparison["comparison"]["delta_time_sec"],
                "color": comparison["comparison"]["color"],
            },
        }

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }
