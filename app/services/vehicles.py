from app.core.state import rt
from app.services.gtfs_rt import fetch_vehicle_positions


def update_vehicles():
    feed = fetch_vehicle_positions()
    vehicles = {}

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue

        v = entity.vehicle

        # Trip é obrigatória
        if not v.trip.trip_id:
            continue

        # Posição é obrigatória
        if not v.position.latitude or not v.position.longitude:
            continue

        vehicle_id = (
            v.vehicle.id
            or v.vehicle.label
            or entity.id
        )

        vehicles[vehicle_id] = {
            # Identificação
            "vehicle_id": vehicle_id,
            "prefixo": v.vehicle.label or v.vehicle.id,

            # Linha / viagem
            "trip_id": v.trip.trip_id,
            "route_id": v.trip.route_id,
            "direction_id": v.trip.direction_id,

            # Localização
            "lat": v.position.latitude,
            "lon": v.position.longitude,

            # Dinâmica
            "speed_mps": v.position.speed if v.position.HasField("speed") else None,
            "bearing": v.position.bearing if v.position.HasField("bearing") else None,

            # Tempo
            "timestamp": v.timestamp,
        }

    rt.vehicles.clear()
    rt.vehicles.update(vehicles)
    print(">>> vehicles inside update:", len(rt.vehicles))
