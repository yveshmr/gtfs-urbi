from __future__ import annotations

from typing import List, Optional, Dict

from pydantic import BaseModel

from app.core.state import rt


class RouteDirection(BaseModel):
    direction_id: int
    shape_id: str


class MapRoute(BaseModel):
    route_id: str
    route_short_name: Optional[str]
    route_long_name: Optional[str]

    directions: List[RouteDirection]


def _build_route_direction_index() -> Dict[str, Dict[int, str]]:
    """
    Converte o índice existente:
        "routeid_direction" -> shape

    PARA

        route_id -> {direction_id -> shape}
    """

    grouped: Dict[str, Dict[int, str]] = {}

    for key, shape_id in rt.route_shapes.items():

        # formato esperado: "{route_id}_{direction_id}"
        if "_" not in key:
            continue

        route_id, direction_str = key.split("_", 1)

        try:
            direction_id = int(direction_str)
        except ValueError:
            continue

        if route_id not in grouped:
            grouped[route_id] = {}

        grouped[route_id][direction_id] = shape_id

    return grouped


def get_all_map_routes() -> List[MapRoute]:
    """
    Constrói a lista de rotas para a visão de Mapa.
    """

    routes: List[MapRoute] = []

    route_dir_index = _build_route_direction_index()

    for route_id, route_obj in rt.routes.items():

        # extrair campos independentemente do tipo
        if hasattr(route_obj, "route_short_name"):
            route_short = route_obj.route_short_name
            route_long = getattr(route_obj, "route_long_name", None)
        else:
            route_short = route_obj.get("route_short_name")
            route_long = route_obj.get("route_long_name")

        #
        # pegar directions reais
        #
        dir_map = route_dir_index.get(route_id, {})

        directions = [
            RouteDirection(direction_id=d, shape_id=s)
            for d, s in sorted(dir_map.items())
        ]

        #
        # montar DTO
        #
        routes.append(
            MapRoute(
                route_id=route_id,
                route_short_name=route_short,
                route_long_name=route_long,
                directions=directions,
            )
        )

    #
    # ordenar por short name (quando existir)
    #
    routes.sort(key=lambda r: (r.route_short_name or ""))

    return routes
