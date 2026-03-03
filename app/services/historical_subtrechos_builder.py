from pathlib import Path
from datetime import datetime
import pickle

import pandas as pd

from app.core.state import rt
from app.core.config import DATA_DIR


# ============================
# Configuração
# ============================

HIST_SOURCE_DIR = DATA_DIR / "subtrechos"
CACHE_DIR = DATA_DIR / "cache" / "historical_subtrechos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================
# Utilidades
# ============================

def _confidence(n: int) -> str:
    if n < 10:
        return "low"
    if n < 30:
        return "medium"
    return "high"


def _slot_15min(ts: pd.Timestamp) -> int:
    return ts.hour * 4 + ts.minute // 15


def _normalize_timestamp(df: pd.DataFrame) -> pd.Series:
    """
    Normaliza timestamp histórico para UTC-aware Timestamp.
    Aceita:
      - ts_utc (ISO 8601 com timezone)
      - timestamp (epoch seconds)
    """
    if "ts_utc" in df.columns:
        return pd.to_datetime(
            df["ts_utc"],
            utc=True,
            errors="coerce",
        )

    if "timestamp" in df.columns:
        return pd.to_datetime(
            df["timestamp"],
            unit="s",
            utc=True,
            errors="coerce",
        )

    return pd.Series([pd.NaT] * len(df))

def _latest_mtime(paths: list[Path]) -> float:
    """Retorna o maior mtime entre arquivos, ou 0 se não houver."""
    if not paths:
        return 0.0
    return max(p.stat().st_mtime for p in paths if p.exists())

# ============================
# Builder principal
# ============================

def build_historical_subtrechos():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"historical_{today}.pkl"

    print(f"[historical] DATA_DIR={DATA_DIR}")
    print(f"[historical] HIST_SOURCE_DIR={HIST_SOURCE_DIR}")
    print(f"[historical] CACHE_DIR={CACHE_DIR}")

    files = sorted(HIST_SOURCE_DIR.glob("*.csv"))
    src_latest = _latest_mtime(files)

    # --------------------------------------------------
    # Cache diário (robusto)
    # --------------------------------------------------
    if cache_file.exists():
        cache_mtime = cache_file.stat().st_mtime
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)

            cached_len = len(cached) if isinstance(cached, dict) else 0

            print(
                f"[historical] cache encontrado: {cache_file.name} | "
                f"{cached_len} chaves | src_files={len(files)}"
            )

            cache_is_empty = cached_len == 0

            # A) cache vazio + existe fonte => rebuild
            if cache_is_empty and len(files) > 0:
                print("[historical][warn] cache vazio, mas há CSVs na fonte -> rebuild")

            # B) fonte mais nova que cache => rebuild
            elif src_latest > cache_mtime:
                print("[historical][warn] fonte mais nova que cache -> rebuild")

            else:
                rt.historical_subtrechos = cached
                return

        except Exception as e:
            print(f"[historical][warn] erro ao carregar cache {cache_file.name}: {e}")
            print("[historical] rebuild devido a falha ao carregar cache")

    # --------------------------------------------------
    # Build (primeira execução ou rebuild)
    # --------------------------------------------------
    print("[historical] iniciando build histórico")
    print(f"[historical] arquivos encontrados: {len(files)}")

    acc = {}

    files_ok = 0
    rows_total = 0
    rows_used = 0

    for file in files:
        try:
            df = pd.read_csv(file)
        except Exception as e:
            print(f"[historical][warn] erro ao ler {file.name}: {e}")
            continue

        rows_total += len(df)

        if "s1" not in df.columns or "s2" not in df.columns:
            continue

        df["timestamp_norm"] = _normalize_timestamp(df)
        df = df.dropna(subset=["timestamp_norm"])

        # dias úteis (UTC) — mantive como está por enquanto
        df = df[df["timestamp_norm"].dt.weekday < 5]

        if df.empty:
            continue

        df["slot"] = df["timestamp_norm"].apply(_slot_15min)

        files_ok += 1

        for _, row in df.iterrows():
            s1 = str(row["s1"])
            s2 = str(row["s2"])
            slot = int(row["slot"])

            time_sec = None
            n_samples = 1

            # Base histórica consolidada
            if "avg_sec_10m" in row and pd.notna(row["avg_sec_10m"]):
                time_sec = float(row["avg_sec_10m"])
                if "n_samples" in row and pd.notna(row["n_samples"]):
                    n_samples = int(row["n_samples"])

            # Base realtime persistida
            elif "speed_avg_kmh" in row and pd.notna(row["speed_avg_kmh"]):
                speed = float(row["speed_avg_kmh"])
                if speed <= 0:
                    continue

                st = rt.subtrechos_all.get((s1, s2))
                if not st:
                    continue

                dist = st.distance_m
                time_sec = (dist / 1000) / speed * 3600

                if "n" in row and pd.notna(row["n"]):
                    n_samples = int(row["n"])

            if time_sec is None:
                continue

            acc.setdefault((s1, s2, slot), []).append((time_sec, n_samples))
            rows_used += 1

    print(
        f"[historical] arquivos válidos: {files_ok} | "
        f"linhas lidas: {rows_total} | "
        f"linhas usadas: {rows_used}"
    )

    historical = {}

    for (s1, s2, slot), values in acc.items():
        total_weight = 0
        weighted_time = 0

        for time_sec, n in values:
            weighted_time += time_sec * n
            total_weight += n

        if total_weight == 0:
            continue

        avg_time = weighted_time / total_weight

        st = rt.subtrechos_all.get((s1, s2))
        if not st or avg_time <= 0:
            continue

        dist = st.distance_m
        avg_speed = (dist / avg_time) * 3.6

        historical[(s1, s2, slot)] = {
            "avg_time_sec": avg_time,
            "avg_speed_kmh": avg_speed,
            "n_samples": total_weight,
            "confidence": _confidence(total_weight),
        }

    rt.historical_subtrechos = historical

    # C) não salvar cache vazio
    if len(historical) == 0:
        print("[historical][warn] build vazio; NÃO salvando cache para não travar o dia")
        return

    with open(cache_file, "wb") as f:
        pickle.dump(historical, f)

    print(
        f"[historical] build concluído | "
        f"subtrechos: {len(historical)} | "
        f"cache salvo em {cache_file.name}"
    )