from app.core.state import rt


def get_stop_times_for_trip(trip_id: str):
    """
    Retorna a sequência de paradas de uma trip,
    já ordenadas por stop_sequence.
    """

    stops = rt.stop_times.get(trip_id)

    if not stops:
        return []

    sorted_stops = sorted(stops, key=lambda x: x["stop_sequence"])

    return sorted_stops
