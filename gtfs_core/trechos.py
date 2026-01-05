from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Trecho:
    """Um trecho operacional definido por um par de paradas."""
    stop_id_origem: str
    stop_id_destino: str
    shape_id: str  # opcional se trabalhar por shape


def carregar_trechos_dos_pairs(pairs: List[Tuple[str, str]], shape_id: str) -> List[Trecho]:
    """
    Converte os PARES definidos no código monolítico em objetos Trecho.
    """
    return [
        Trecho(
            stop_id_origem=o,
            stop_id_destino=d,
            shape_id=shape_id
        )
        for (o, d) in pairs
    ]
