from fastapi import APIRouter
from typing import List

from app.services.map_shapes import MapShape, get_all_map_shapes


router = APIRouter(
    prefix="/map",
    tags=["map"],
)


@router.get("/shapes", response_model=List[MapShape])
def list_map_shapes():
    """
    Retorna todas as shapes do GTFS estático,
    no formato amigável ao frontend de mapa.
    """
    return get_all_map_shapes()
