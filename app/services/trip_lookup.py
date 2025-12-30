import csv
from pathlib import Path
from app.core.config import GTFS_DIR


def load_trips():
    """
    Carrega trips.txt do GTFS estático
    e retorna dict trip_id -> {route_id, service_id, shape_id, direction_id}
    """

    trips_path = GTFS_DIR / "trips.txt"

    trips = {}

    with open(trips_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            trip_id = row["trip_id"]

            trips[trip_id] = {
                "route_id": row.get("route_id"),
                "service_id": row.get("service_id"),
                "shape_id": row.get("shape_id"),
                "direction_id": int(row["direction_id"]) if row.get("direction_id") else None,
            }

    return trips


def build_route_shape_index(trips):
    """
    Cria mapa:
        (route_id, direction_id) -> shape_id
    """

    mapping = {}

    for t in trips.values():
        rid = t["route_id"]
        did = t["direction_id"]
        sid = t["shape_id"]

        if not rid or did is None or not sid:
            continue

        key = f"{rid}_{did}"
        mapping[key] = sid

    return mapping


def get_trips_for_route(route_id: str, direction_id: int):
    """
    Retorna todas trips de uma rota/direção
    """

    trips = []

    from app.core.state import rt

    for tid, t in rt.trips.items():
        if t["route_id"] == route_id and t["direction_id"] == direction_id:
            trips.append({"trip_id": tid, "shape_id": t["shape_id"]})

    return trips
