import logging
from typing import Dict, List, Optional

from app.core.state import rt
from gtfs_core.pipeline_trechos import Subtrecho

logger = logging.getLogger(__name__)

"""
Realtime Subtrechos

✔ (shape_id, shape_pos_m) → Subtrecho
"""

# shape_id -> lista ordenada por m1
subtrechos_by_shape: Dict[str, List[Subtrecho]] = {}


def build_subtrecho_index():
    """
    Constrói índice de subtrechos agrupado por shape_id.
    """

    global subtrechos_by_shape
    subtrechos_by_shape.clear()

    for s in rt.subtrechos:
        if not s.shape_id:
            continue

        subtrechos_by_shape.setdefault(s.shape_id, []).append(s)

    # ordenar
    for sid, lst in subtrechos_by_shape.items():
        lst.sort(key=lambda x: x.m1)

    logger.info(
        f"Índice de subtrechos criado: "
        f"{len(subtrechos_by_shape)} shapes indexados"
    )


def find_subtrecho_for_position(
    shape_id: str,
    shape_pos_m: float
) -> Optional[Subtrecho]:

    lst = subtrechos_by_shape.get(shape_id)
    if not lst:
        return None

    for s in lst:
        if s.m1 <= shape_pos_m < s.m2:
            return s

    return None
