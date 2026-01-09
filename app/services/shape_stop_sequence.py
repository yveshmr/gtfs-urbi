import logging
from typing import Dict

from app.core.state import rt

logger = logging.getLogger(__name__)


def build_shape_stop_sequence():
    """
    Constrói:
        rt.shape_stop_sequence
    Formato:
        shape_id -> { stop_id -> stop_sequence }
    """

    shape_seq: Dict[str, Dict[str, int]] = {}

    for trip_id, stops in rt.stop_times.items():
        trip = rt.trips.get(trip_id)
        if not trip:
            continue

        shape_id = trip.get("shape_id")
        if not shape_id:
            continue

        seq_map = shape_seq.setdefault(shape_id, {})

        last_stop = None
        order = len(seq_map)

        for st in stops:
            stop_id = st["stop_id"]

            # remove duplicatas consecutivas (igual ao monolítico)
            if stop_id == last_stop:
                continue

            if stop_id not in seq_map:
                seq_map[stop_id] = order
                order += 1

            last_stop = stop_id

    rt.shape_stop_sequence = shape_seq

    logger.info(
        f"shape_stop_sequence criado: {len(shape_seq)} shapes"
    )
