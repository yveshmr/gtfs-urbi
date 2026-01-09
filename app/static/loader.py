import pandas as pd
from pathlib import Path

from app.core.config import GTFS_DIR


def read_csv(name: str) -> pd.DataFrame:
    """
    Lê um arquivo CSV do GTFS estático JÁ EXTRAÍDO em disco.

    Exemplo:
        read_csv("stops.txt")
        read_csv("shapes.txt")
    """

    path = GTFS_DIR / name

    if not path.exists():
        raise FileNotFoundError(f"Arquivo GTFS não encontrado: {path}")

    return pd.read_csv(path)
