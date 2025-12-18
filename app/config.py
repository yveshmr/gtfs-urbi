from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BASE_DIR / "data"
GTFS_DIR = DATA_DIR / "gtfs"

GTFS_STATIC_URL = "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip"
GTFS_RT_VEHICLE_POSITIONS_URL = "https://servicos.cittati.com.br/GTFS-RT2/URBI/vehicle-positions"

