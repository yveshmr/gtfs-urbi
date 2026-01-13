from fastapi import APIRouter
from typing import List, Dict

from app.core.state import rt


router = APIRouter(
    prefix="/map",
    tags=["map-subtrechos-all-speed"]
)


@router.get("/subtrechos/all")
def list_all_subtrechos_with_speed() -> List[Dict]:
    """
    Retorna TODOS os subtrechos possíveis do GTFS
    com velocidade média calculada (modelo ALL).

    - Usa subtrechos globais (menor shape)
    - Junta com estatísticas de velocidade (15 min)
    - Retorna JSON pronto para o mapa
    """

    out: List[Dict] = []

    # Segurança
    if not hasattr(rt, "subtrechos_all"):
        return out

    stats = getattr(rt, "subtrecho_all_stats", {})
    if not stats:
        return out

    for key, st in rt.subtrechos_all.items():

        stat = stats.get(key)
        if not stat:
            continue

        if not st.polyline or len(st.polyline) < 2:
            continue

        s1, s2 = key

        out.append({
            "subtrecho_id": f"{s1}->{s2}",
            "coords": [[lat, lon] for (lat, lon) in st.polyline],

            # velocidade média do período (janela)
            "speed_kmh": stat.get("speed_avg_kmh"),

            # metadados
            "n": stat.get("n", 0),
            "last_ts": stat.get("last_ts"),
            "model": "all",
            "from_stop": s1,
            "to_stop": s2,

            # distância do trecho (do ALL)
            "distance_m": round(st.distance_m, 1),

            # ============================
            # CAMPOS PARA DEBUG DO CÁLCULO
            # ============================
            # dt usado na última medição que entrou na janela
            "dt_sec": stat.get("dt_sec"),

            # timestamps da última medição (entrada/saída)
            "t0_ts": stat.get("t0_ts"),
            "t1_ts": stat.get("t1_ts"),

            # velocidade instantânea da última medição
            "speed_last_kmh": stat.get("speed_last_kmh"),

            # ✅ quando a medição foi descartada (ex: > 70 km/h)
            "discarded": stat.get("discarded"),
        })

    return out
