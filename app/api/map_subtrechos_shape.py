from fastapi import APIRouter
from app.core.state import rt

router = APIRouter(prefix="/map", tags=["subtrechos-shape"])


@router.get("/subtrechos/shape")
def list_subtrechos_shape():

    out = []

    stats = getattr(rt, "subtrecho_shape_stats", {})
    if not stats:
        return out

    for st in rt.subtrechos_shape:
        key = (st.s1, st.s2)
        stat = stats.get(key)
        if not stat:
            continue

        out.append({
            "subtrecho_id": f"{st.s1}->{st.s2}",
            "coords": st.polyline,
            "speed_kmh": stat["speed_avg_kmh"],
            "n": stat["n"],
            "last_ts": stat["last_ts"],
            "model": "shape",
        })

    return out
