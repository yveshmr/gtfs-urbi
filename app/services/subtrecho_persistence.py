import time
import csv
from pathlib import Path

from app.core.state import rt


# =============================================================================
# Persistência do histórico de subtrechos (CSV)
# =============================================================================

# ✅ Caminho fixo relativo ao repo: .../gtfs-urbi/data/subtrechos
# Isso evita salvar em lugares diferentes dependendo de onde você rodar o uvicorn.
BASE_DIR = Path(__file__).resolve().parents[2]  # .../gtfs-urbi
PERSIST_DIR = BASE_DIR / "data" / "subtrechos"
PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# ✅ Salvar a cada 10 minutos
WINDOW_SEC = 10 * 60  # 600s


async def persist_subtrechos_loop():
    print("🟢 Iniciando tarefa de persistência de subtrechos...")

    while True:
        try:
            persist_snapshot()
        except Exception as e:
            print(f"⚠️ Erro na persistência de subtrechos: {e}")

        await sleep_async(WINDOW_SEC)


def persist_snapshot():
    ts = int(time.time())
    fname = PERSIST_DIR / f"subtrechos_{ts}.csv"

    # ✅ IMPORTANTÍSSIMO:
    # O runtime atual acumula estatísticas em rt.subtrecho_all_stats (não subtrecho_stats).
    stats = getattr(rt, "subtrecho_all_stats", {})
    if not stats:
        # Sem dados acumulados ainda → não cria arquivo
        return

    # Índice rápido: (s1, s2) -> shape_id (se existir)
    # Obs: em alguns estados do runtime, rt.subtrechos pode não existir; por isso o getattr().
    shape_index = {
        (st.s1, st.s2): st.shape_id
        for st in getattr(rt, "subtrechos", [])
        if getattr(st, "shape_id", None)
    }

    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # ✅ Colunas:
        # - distance_m e dt_sec são os insumos de cálculo que você pediu (já vêm no stat)
        writer.writerow([
            "timestamp",
            "s1",
            "s2",
            "shape_id",
            "distance_m",
            "dt_sec",
            "speed_avg_kmh",
            "n",
            "last_ts",
        ])

        for (s1, s2), stat in stats.items():
            writer.writerow([
                ts,
                s1,
                s2,
                shape_index.get((s1, s2)),
                stat.get("distance_m"),
                stat.get("dt_sec"),
                stat.get("speed_avg_kmh"),
                stat.get("n"),
                stat.get("last_ts"),
            ])


async def sleep_async(seconds: int):
    import asyncio
    await asyncio.sleep(seconds)