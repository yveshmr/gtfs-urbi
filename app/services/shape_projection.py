from app.core.state import rt
from app.geometry.distance import haversine_m


def project_vehicle_on_shape(vehicle: dict) -> float:
    """
    Recebe veículo com lat/lon e retorna posição em metros ao longo do shape.
    """

    trip_id = vehicle.get("trip_id")
    if not trip_id:
        return None

    trip = rt.trips.get(trip_id)
    if not trip:
        return None

    shape_id = trip.get("shape_id")
    if not shape_id:
        return None

    shape = rt.shapes.get(shape_id)
    if not shape:
        return None

    vlat = vehicle["lat"]
    vlon = vehicle["lon"]

    best_dist = float("inf")
    best_m = None

    for (lat, lon, m) in shape:
        d = haversine_m(vlat, vlon, lat, lon)
        if d < best_dist:
            best_dist = d
            best_m = m

    return best_m
