import io
import zipfile
import httpx
import pandas as pd
from app.core.config import URL_GTFS_STATIC_ZIP


def download_gtfs_zip() -> zipfile.ZipFile:
    resp = httpx.get(URL_GTFS_STATIC_ZIP, timeout=60)
    resp.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(resp.content))


def read_csv(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
    with zf.open(name) as f:
        return pd.read_csv(f)
