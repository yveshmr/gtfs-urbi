import math
from app.core.state import rt


def haversine(lat1, lon1, lat2, lon2):
    """
    Retorna distância em metros
    """
    R = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )

    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_shape_length(points):
    """
    points = lista de dicts:
    { "lat": float, "lon": float }

    retorna comprimento total do shape em metros
    """

    if not points or len(points) < 2:
        return 0

    total = 0.0

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        total += haversine(
            p1["lat"],
            p1["lon"],
            p2["lat"],
            p2["lon"],
        )

    return total


def project_progress(lat, lon, points):
    """
    Encontra o ponto do shape mais próximo
    e calcula a distância desde o início
    """

    if not points or len(points) == 0:
        return None

    closest_index = None
    closest_dist = 999999999

    for i, p in enumerate(points):
        d = haversine(lat, lon, p["lat"], p["lon"])
        if d < closest_dist:
            closest_dist = d
            closest_index = i

    dist = 0.0
    for i in range(closest_index):
        dist += haversine(
            points[i]["lat"],
            points[i]["lon"],
            points[i + 1]["lat"],
            points[i + 1]["lon"],
        )

    return dist


def compute_vehicle_progress(v):
    """
    Calcula progresso do veículo via:
      route_id + direction_id → shape_id
      shape → polyline
      posição do veículo → distância percorrida
    """

    route_id = v.get("route_id")
    direction_id = v.get("direction_id")
    lat = v.get("lat")
    lon = v.get("lon")

    if not route_id or direction_id is None:
        return None

    key = f"{route_id}_{direction_id}"

    shape_id = rt.route_shapes.get(key)
    if not shape_id:
        return None

    shape = rt.shapes.get(shape_id)
    if not shape:
        return None

    total_m = compute_shape_length(shape)

    pos_m = None
    if lat and lon:
        pos_m = project_progress(lat, lon, shape)

    progress = None
    if total_m and pos_m is not None:
        progress = pos_m / total_m
        progress = max(0.0, min(1.0, progress))

    return {
        "shape_id": shape_id,
        "shape_len_m": total_m,
        "shape_pos_m": pos_m,
        "progress": progress,
    }
