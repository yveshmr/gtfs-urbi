from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd

from app.core.state import rt


# =========================================================
# UTILIDADES
# =========================================================

def _slot_15min(ts: pd.Timestamp) -> int:
    return ts.hour * 4 + ts.minute // 15


def _classify_ratio(ratio: float) -> str:
    """
    Classificação de cor conforme regra definida.
    """
    if ratio < 0.55:
        return "purple"      # problema viário
    if ratio < 0.65:
        return "red"         # engarrafamento
    if ratio < 0.85:
        return "orange"      # grande lentidão
    if ratio < 0.95:
        return "yellow"      # lentidão
    if ratio <= 1.10:
        return "green"       # dentro do esperado
    return "dark_green"      # acima do esperado


# =========================================================
# FUNÇÃO PRINCIPAL DE COMPARAÇÃO
# =========================================================

def compare_realtime_with_historical(
    s1: str,
    s2: str,
    realtime_speed_kmh: float,
    realtime_timestamp_utc: datetime,
) -> Optional[Dict]:
    """
    Compara uma medição realtime com a média histórica canônica.

    Regras:
    - Histórico só vale se existir no ALL (Opção A)
    - Slot de 15 minutos
    - Fallback: tenta slot posterior, depois anterior (1 passo)
    - Se não encontrar histórico -> retorna None (camada cinza)

    Retorno:
        dict com métricas prontas para o mapa
        ou None se não houver histórico válido
    """

    if realtime_speed_kmh <= 0:
        return None

    # normalização defensiva
    s1 = str(s1)
    s2 = str(s2)

    # -----------------------------------------------------
    # Subtrecho canônico (ALL)
    # -----------------------------------------------------
    st = rt.subtrechos_all.get((s1, s2))
    if not st:
        return None

    # -----------------------------------------------------
    # Slot
    # -----------------------------------------------------
    ts = pd.to_datetime(realtime_timestamp_utc, utc=True)
    slot = _slot_15min(ts)

    # -----------------------------------------------------
    # Histórico (slot + fallback)
    # -----------------------------------------------------
    hist = rt.historical_subtrechos.get((s1, s2, slot))

    if not hist:
        # fallback posterior
        hist = rt.historical_subtrechos.get((s1, s2, slot + 1))

    if not hist:
        # fallback anterior
        hist = rt.historical_subtrechos.get((s1, s2, slot - 1))

    if not hist:
        return None

    # -----------------------------------------------------
    # Métricas
    # -----------------------------------------------------
    hist_speed = hist["avg_speed_kmh"]
    hist_time = hist["avg_time_sec"]
    n_samples = hist["n_samples"]
    confidence = hist["confidence"]

    # tempo realtime (canônico)
    dist_m = st.distance_m
    realtime_time_sec = (dist_m / 1000) / realtime_speed_kmh * 3600

    # razão e diferença absoluta
    ratio = realtime_speed_kmh / hist_speed if hist_speed > 0 else None
    delta_speed = realtime_speed_kmh - hist_speed
    delta_time_sec = realtime_time_sec - hist_time

    if ratio is None:
        return None

    color = _classify_ratio(ratio)

    # -----------------------------------------------------
    # Payload final (pronto para o mapa)
    # -----------------------------------------------------
    return {
        "s1": s1,
        "s2": s2,
        "slot": slot,
        "realtime": {
            "speed_kmh": realtime_speed_kmh,
            "time_sec": realtime_time_sec,
            "timestamp": ts.isoformat(),
        },
        "historical": {
            "avg_speed_kmh": hist_speed,
            "avg_time_sec": hist_time,
            "n_samples": n_samples,
            "confidence": confidence,
        },
        "comparison": {
            "ratio": ratio,
            "delta_speed_kmh": delta_speed,
            "delta_time_sec": delta_time_sec,
            "color": color,
        },
    }
