from __future__ import annotations

from typing import List, Tuple, Optional

from pydantic import BaseModel

from app.core.state import rt


class MapShape(BaseModel):
    """
    Representa uma polyline de shape GTFS
    para consumo no frontend de mapa.
    """

    shape_id: str
    points: List[Tuple[float, float]]  # (lat, lon)


def get_all_map_shapes() -> List[MapShape]:
    """
    Converte as shapes do GTFS estático para DTOs
    utilizados na visão de mapa.

    As shapes já estão carregadas em memória.
    """

    shapes: List[MapShape] = []

    for shape_id, pts in rt.shapes.items():

        # garantimos formato (lat, lon)
        coords = [(p.lat, p.lon) if hasattr(p, "lat") else (p[0], p[1]) for p in pts]

        shapes.append(
            MapShape(
                shape_id=shape_id,
                points=coords
            )
        )

    return shapes
