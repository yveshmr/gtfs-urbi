import logging
from typing import Dict, List, Optional

from app.core.state import rt
from gtfs_core.pipeline_trechos import Subtrecho

logger = logging.getLogger(__name__)

"""
Realtime Subtrechos

Responsabilidade deste módulo:

✔ fornecer lookup eficiente:
    (shape_id, shape_pos_m) → Subtrecho

❗ Nesta primeira fase:
- NÃO altera estado global
- NÃO calcula tempos
- NÃO impacta backend existente
"""

# shape_id -> lista ordenada de subtrechos
subtrechos_by_shape: Dict[str, List[Subtrecho]] = {}


def build_subtrecho_index():
    """
    Constrói índice em memória agrupando subtrechos por shape.

    Observação:
    O pipeline original não salva shape_id em cada Subtrecho,
    então nesta fase manteremos apenas o agrupamento base.
    """
    global subtrechos_by_shape

    subtrechos_by_shape.clear()

    for s in rt.subtrechos:
        # Por enquanto agrupamos apenas por group
        # pois shape_id ainda não está disponível no objeto
        subtrechos_by_shape.setdefault(s.group, []).append(s)

    logger.info(
        f"Índice inicial de subtrechos criado "
        f"({len(subtrechos_by_shape)} grupos)"
    )


def find_subtrecho_for_position(
    shape_id: str,
    shape_pos_m: float
) -> Optional[Subtrecho]:
    """
    Localiza o subtrecho correspondente à posição do veículo.

    Nesta versão inicial, ainda não temos shape_pos acumulado
    nos objetos, então retornamos None.
    """
    return None
