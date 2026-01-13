import logging
from typing import Dict, List, Optional
from datetime import datetime

from app.core.state import rt
from gtfs_core.pipeline_trechos import Subtrecho
from app.services.subtrechos_comparator import compare_realtime_with_historical

logger = logging.getLogger(__name__)

subtrechos_by_shape: Dict[str, List[Subtrecho]] = {}


def build_subtrecho_index():
    global subtrechos_by_shape
    subtrechos_by_shape.clear()

    for s in rt.subtrechos:
        if not s.shape_id:
            continue
        subtrechos_by_shape.setdefault(s.shape_id, []).append(s)

    for lst in subtrechos_by_shape.values():
        lst.sort(key=lambda x: x.m1)

    logger.info(
        f"Índice de subtrechos: {len(subtrechos_by_shape)} shapes"
    )


def find_subtrecho_for_position(
    shape_id: str,
    shape_pos_m: float,
    *,
    realtime_speed_kmh: Optional[float] = None,
    realtime_timestamp_utc: Optional[datetime] = None,
) -> Optional[Subtrecho]:
    """
    Retorna o subtrecho correspondente à posição no shape.
    Se velocidade e timestamp forem informados, executa
    a comparação histórico × realtime e anexa ao subtrecho.
    """

    lst = subtrechos_by_shape.get(shape_id)
    if not lst:
        return None

    for s in lst:
        if s.m1 <= shape_pos_m < s.m2:

            # --------------------------------------------------
            # Integração da comparação histórico × realtime
            # --------------------------------------------------
            if (
                realtime_speed_kmh is not None
                and realtime_timestamp_utc is not None
            ):
                try:
                    comparison = compare_realtime_with_historical(
                        s1=str(s.s1),
                        s2=str(s.s2),
                        realtime_speed_kmh=realtime_speed_kmh,
                        realtime_timestamp_utc=realtime_timestamp_utc,
                    )
                except Exception as e:
                    logger.warning(
                        f"Erro ao comparar histórico x realtime "
                        f"({s.s1}->{s.s2}): {e}"
                    )
                    comparison = None

                # anexa dinamicamente (não quebra modelo)
                s.comparison = comparison

            return s

    return None
