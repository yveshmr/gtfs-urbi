import requests
from zipfile import ZipFile
from io import BytesIO
from pathlib import Path
from datetime import datetime

from app.core.config import GTFS_DIR, GTFS_STATIC_URL


VERSION_FILE = GTFS_DIR / "version.txt"


def _today_str():
    """
    Retorna a data de hoje no formato YYYY-MM-DD
    (pode alterar futuramente para timezone-aware se quiser)
    """
    return datetime.now().strftime("%Y-%m-%d")


def _load_local_version():
    """
    Lê a data do último download, se existir.
    """
    if not VERSION_FILE.exists():
        return None

    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except:
        return None


def _save_local_version(date_str: str):
    """
    Salva a data do último download.
    """
    GTFS_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(date_str, encoding="utf-8")


def _download_and_extract():
    print("⬇️ Baixando GTFS estático...")

    resp = requests.get(GTFS_STATIC_URL, timeout=60)
    resp.raise_for_status()

    zip_bytes = resp.content

    # salva o zip original
    (GTFS_DIR / "static.zip").write_bytes(zip_bytes)

    # extrai
    z = ZipFile(BytesIO(zip_bytes))
    z.extractall(GTFS_DIR)

    today = _today_str()
    _save_local_version(today)

    print(f"✅ GTFS atualizado ({today}) em {GTFS_DIR}")


def ensure_gtfs_static():
    """
    Garante que o GTFS estático esteja atualizado no dia.

    Regras:
      - se não existir → baixa
      - se versão != hoje → baixa
      - se versão == hoje → não baixa
    """

    GTFS_DIR.mkdir(parents=True, exist_ok=True)

    local_version = _load_local_version()
    today = _today_str()

    if local_version == today:
        print(f"ℹ️ GTFS já está atualizado ({today}), pulando download")
        return

    # ou nunca baixado
    _download_and_extract()
