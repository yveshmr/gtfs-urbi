from fastapi import APIRouter
from typing import List

from app.services.map_routes import MapRoute, get_all_map_routes


router = APIRouter(
    prefix="/map",
    tags=["map"],
)


@router.get("/routes", response_model=List[MapRoute])
def list_map_routes():
    """
    Retorna as linhas (routes) GTFS estruturadas
    para uso no frontend de mapa.
    """
    return get_all_map_routes()
