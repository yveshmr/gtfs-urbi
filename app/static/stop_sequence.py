from app.core.state import rt

def find_stop_sequence(route_id: str, stop_id: str, direction_id: int = None):
    """
    Resolve o stop_sequence de um veículo baseado no
    GTFS estático, usando route_id + stop_id (+ direction opcional).
    """

    # 1️⃣ filtra trips daquela rota
    trip_candidates = [
        tid for tid, tdata in rt.trips.items()
        if tdata.get("route_id") == route_id
    ]

    # 2️⃣ dentro desses trips, filtra os que contém o stop_id
    valid = []
    for tid in trip_candidates:
        stops = rt.stop_times.get(tid, [])
        if stop_id in stops:
            valid.append(tid)

    if not valid:
        return None, []

    # 3️⃣ se direction importar:
    if direction_id in (0, 1):
        valid = [
            tid for tid in valid
            if rt.trips[tid].get("direction_id") == direction_id
        ] or valid

    # 4️⃣ pegar primeiro candidato
    best_trip = valid[0]
    seq = rt.stop_times[best_trip].index(stop_id)

    return seq, valid
