from pathlib import Path
import os

#
# Diretórios base
#
BASE_DIR = Path(__file__).resolve().parents[2]

# Permite override por variável de ambiente
_data_dir_env = os.getenv("DATA_DIR")

if _data_dir_env:
    DATA_DIR = Path(_data_dir_env)
else:
    DATA_DIR = BASE_DIR / "data"

GTFS_DIR = DATA_DIR / "gtfs"

# Garante que existam
DATA_DIR.mkdir(parents=True, exist_ok=True)
GTFS_DIR.mkdir(parents=True, exist_ok=True)

#
# URLs GTFS
#
GTFS_STATIC_URL = "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip"

GTFS_RT_VEHICLE_POSITIONS_URL = (
    "https://servicos.cittati.com.br/GTFS-RT2/URBI/vehicle-positions"
)

# Para compatibilidade com loaders
URL_VEHICLE_POSITIONS = GTFS_RT_VEHICLE_POSITIONS_URL
URL_GTFS_STATIC_ZIP = GTFS_STATIC_URL