from fastapi import APIRouter
from typing import List, Dict

from app.core.state import rt

router = APIRouter(
    prefix="/map",
    tags=["map-subtrechos-shape"]
)


@router.get("/subtrechos/shape")
def list_subtrechos_by_shape() -> List[Dict]:
    """
    Subtrechos com velocidade média calculada por projeção no shape
    (modelo contínuo).
    """

    out = []

    stats = getattr(rt, "subtrecho_stats_by_shape", {})
    if not stats:
        return out

    for st in rt.subtrechos:
        key = (st.s1, st.s2)
        stat = stats.get(key)
        if not stat:
            continue

        if not st.polyline or len(st.polyline) < 2:
            continue

        out.append({
            "subtrecho_id": f"{st.s1}->{st.s2}",
            "coords": [[lat, lon] for (lat, lon) in st.polyline],
            "speed_kmh": stat["speed_avg_kmh"],
            "n": stat.get("n", 0),
            "last_ts": stat.get("last_ts"),
            "model": "shape",
        })

    return out
