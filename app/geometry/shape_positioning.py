from app.core.state import rt
from app.geometry.distance import haversine_m


def project_vehicle_shape_position(shape_id, lat, lon):
    """
    Projeta o veículo ao longo do shape e retorna a distância acumulada (m)
    do ponto mais próximo entre a posição do veículo e os pontos do shape.
    """

    shape = rt.shapes.get(shape_id)
    if not shape:
        return None

    best_shape_m = None
    best_dist = 999999999

    for i in range(len(shape) - 1):

        lat1, lon1, m1 = shape[i]
        lat2, lon2, m2 = shape[i + 1]

        d1 = haversine_m(lat, lon, lat1, lon1)
        if d1 < best_dist:
            best_dist = d1
            best_shape_m = m1

        d2 = haversine_m(lat, lon, lat2, lon2)
        if d2 < best_dist:
            best_dist = d2
            best_shape_m = m2

    return best_shape_m
