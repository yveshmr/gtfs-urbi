import time
import csv
from pathlib import Path

from app.core.state import rt


PERSIST_DIR = Path("data/subtrechos")
PERSIST_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_SEC = 60 *15  # snapshot a cada 15 minutos


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

    # ✅ FIX 3: o runtime atual acumula em rt.subtrecho_all_stats (não em subtrecho_stats)
    stats = getattr(rt, "subtrecho_all_stats", {})
    
    if not stats:
        return

    # índice rápido: (s1, s2) -> shape_id
    shape_index = {
        (st.s1, st.s2): st.shape_id
        for st in getattr(rt, "subtrechos", [])
        if st.shape_id
    }

    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "timestamp",
            "s1",
            "s2",
            "shape_id",
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
                stat.get("speed_avg_kmh"),
                stat.get("n"),
                stat.get("last_ts"),
            ])


async def sleep_async(seconds: int):
    import asyncio
    await asyncio.sleep(seconds)
