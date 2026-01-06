from fastapi import APIRouter
from typing import List

from app.services.map_vehicles import MapVehicle, get_active_map_vehicles


router = APIRouter(
    prefix="/map",
    tags=["map"],
)


@router.get("/vehicles", response_model=List[MapVehicle])
def list_map_vehicles():
    """
    Endpoint utilizado pelo frontend do MAPA.

    Retorna a lista de veículos ativos, já estruturada e enriquecida
    com informações do GTFS estático.
    """
    return get_active_map_vehicles()
