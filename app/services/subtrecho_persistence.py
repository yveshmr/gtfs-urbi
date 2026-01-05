import json
import os
import time
import asyncio
from datetime import datetime

from app.core.state import rt


SAVE_INTERVAL_SEC = 60  # executa TODO MINUTO
WINDOW_SEC = 15 * 60    # mas só grava se mudou a janela


last_save_window = None


def get_output_path():
    os.makedirs("data/subtrechos", exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return f"data/subtrechos/{date_str}.jsonl"


async def persist_subtrechos_loop():
    """
    Tarefa assíncrona que grava periodicamente as médias dos subtrechos,
    similar ao comportamento do monolítico.
    """

    global last_save_window

    print("🟢 Iniciando tarefa de persistência de subtrechos...")

    while True:

        try:
            await asyncio.sleep(SAVE_INTERVAL_SEC)

            now = int(time.time())

            #
            # definimos a janela por múltiplos de 15 min
            #
            window = now - (now % WINDOW_SEC)

            #
            # já gravamos essa janela?
            #
            if last_save_window == window:
                continue

            last_save_window = window

            #
            # nada para salvar?
            #
            if not getattr(rt, "subtrecho_stats", None):
                continue

            path = get_output_path()

            count = 0

            with open(path, "a", encoding="utf-8") as f:

                for key, stats in rt.subtrecho_stats.items():

                    shape_id, s1, s2 = key

                    row = {
                        "shape_id": shape_id,
                        "s1": s1,
                        "s2": s2,
                        "avg_s": stats["avg_s"],
                        "samples": stats["n"],
                        "window_start": stats["window_start"],
                        "window_end": stats["window_end"],
                        "saved_at": now,
                    }

                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1

            print(f"💾 Persistidos {count} subtrechos (janela {window})")

        except Exception as e:
            print(f"⚠️ Erro na persistência de subtrechos: {e}")
