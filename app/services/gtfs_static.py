import requests
from zipfile import ZipFile
from io import BytesIO
from pathlib import Path

from app.core.config import GTFS_DIR, GTFS_STATIC_URL


def ensure_gtfs_static():
    """
    Garante que o GTFS estático exista em disco.
    Se não existir, faz o download e extrai.
    """

    # arquivo obrigatório GTFS
    stops_file = GTFS_DIR / "stops.txt"

    if stops_file.exists():
        print("ℹ️ GTFS estático já existe, pulando download")
        return

    GTFS_DIR.mkdir(parents=True, exist_ok=True)

    print("⬇️ Baixando GTFS estático...")

    resp = requests.get(GTFS_STATIC_URL, timeout=60)
    resp.raise_for_status()

    z = ZipFile(BytesIO(resp.content))
    z.extractall(GTFS_DIR)

    print(f"✅ GTFS estático pronto em {GTFS_DIR}")
