# -*- coding: utf-8 -*-

from pathlib import Path
import pickle
from datetime import datetime

from app.core.state import rt
from gtfs_core.pipeline_trechos import construir_todos_os_subtrechos


CACHE_DIR = Path("data/cache/subtrechos_all")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path() -> Path:
    return CACHE_DIR / f"subtrechos_all_{_today_key()}.pkl"


def build_all_subtrechos():
    """
    Constrói ou carrega TODOS os subtrechos possíveis.
    """

    cache_file = _cache_path()

    if cache_file.exists():
        print("📦 Carregando subtrechos globais do cache diário...")
        with open(cache_file, "rb") as f:
            subtrechos = pickle.load(f)

        rt.subtrechos_all = {
            (st.s1, st.s2): st for st in subtrechos
        }
        return rt.subtrechos_all

    print("🧠 Gerando subtrechos globais (pipeline pesado)...")

    subtrechos = construir_todos_os_subtrechos()

    try:
        with open(cache_file, "wb") as f:
            pickle.dump(subtrechos, f)
        print(f"💾 Cache salvo: {cache_file.name}")
    except Exception as e:
        print(f"⚠️ Falha ao salvar cache: {e}")

    rt.subtrechos_all = {
        (st.s1, st.s2): st for st in subtrechos
    }

    return rt.subtrechos_all
