from zoneinfo import ZoneInfo
import os

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

URL_GTFS_STATIC_ZIP = os.getenv(
    "URL_GTFS_STATIC_ZIP",
    "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip",
)

URL_VEHICLE_POSITIONS = os.getenv(
    "URL_VEHICLE_POSITIONS",
    "https://servicos.cittati.com.br/GTFS-RT2/URBI/vehicle-positions",
)

POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "15"))
STATIC_REFRESH_MIN = int(os.getenv("STATIC_REFRESH_MIN", "60"))
